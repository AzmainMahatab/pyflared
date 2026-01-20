from __future__ import annotations

import re
from typing import Final, NamedTuple
from urllib.parse import ParseResult, parse_qs, urlparse

from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import (
    ConfigIngress,
    ConfigIngressOriginRequest,
)

type Domain = ParseResult

CLOUDFLARE_SUPPORTED_SCHEMES = {"http", "https", "unix", "tcp", "ssh", "rdp", "unix+tls", "smb"}
"""
Supported protocols: http://, https://, unix://, tcp://, ssh://, rdp://,
    unix+tls://, smb://
"""
CLOUDFLARE_HTTP_STATUS_RE = re.compile(r"^http_status:\d+$")
"""
Alternatively can return a HTTP status code
    http_status:[code] e.g. 'http_status:404'.
"""

tcp = "tcp"
PORT_TO_SCHEMES: Final[dict[int, str]] = {
    80: "http", 443: "https", 22: "ssh", 3389: "rdp",
    3306: tcp, 5432: tcp, 6379: tcp, 27017: tcp
}


class Service(ParseResult):
    """
    Extended ParseResult that can self-verify SSL settings and generate Ingress Config.
    """

    def __new__(cls, parsed: ParseResult):
        return super().__new__(cls, *parsed)

    @classmethod
    def autocomplete_from_str(cls, url: str) -> Service:
        """
        Normalizes a lazy input string into a strict ParseResult.
        Handles '8000', 'localhost:8000', 'unix:/path', 'app.com', etc.
        """

        parsed = urlparse(url)
        # According to RFC 3986, underscores are illegal in URI schemes
        if CLOUDFLARE_HTTP_STATUS_RE.match(url):
            return cls(parsed)
        # If user provides a supported scheme (e.g., https://), trust it as is.
        if parsed.scheme in CLOUDFLARE_SUPPORTED_SCHEMES:
            return cls(parsed)

        scheme, netloc, path = parsed.scheme, parsed.netloc, parsed.path

        # The "File Hack": Treat unknown path as File URI to separate Host vs Path
        # logic: file://8000/api       -> netloc="8000", path="/api"
        # logic: file://localhost:8000 -> netloc="localhost:8000", path=""
        # logic: file:///var/run/sock  -> netloc="", path="/var/run/sock"
        file_parsed = urlparse(f"file://{path}")

        # CASE A: Network Location (Host or Port found)
        if file_parsed.netloc:
            # 1. Just a port ("8000")
            if file_parsed.netloc.isdigit():
                port = int(file_parsed.netloc)
                scheme = PORT_TO_SCHEMES.get(port, "http")
                netloc = f"localhost:{port}"
                # Important: Preserve the path (e.g. /api) that followed the port
                path = file_parsed.path

                # 2. Host:Port ("localhost:8000", "my-app:3000")
            else:
                # Re-parse with // to ensure robust port extraction
                temp = urlparse(f"//{file_parsed.netloc}")
                netloc = temp.netloc
                # Logic check: If original had path "localhost:8000/api",
                # file_parsed.path contains "/api". We must use it.
                path = file_parsed.path

                scheme = PORT_TO_SCHEMES.get(temp.port, "http") if temp.port else "http"

        # CASE B: File Path (Unix Socket or Named Pipe)
        elif file_parsed.path:
            if file_parsed.path.startswith("/"):
                # Unix: unix:/var/run/sock
                x = urlparse(f"unix:{file_parsed.path}?{parsed.query}")
                return cls(x)
            if file_parsed.path.startswith("\\\\"):
                # Windows: npipe:\\.\pipe\foo
                x = urlparse(f"npipe:{file_parsed.path}?{parsed.query}")
                return cls(x)

        # Fallback / Final Construction
        final_scheme = scheme if scheme else "http"
        final_url = f"{final_scheme}://{netloc}{path}"

        # Re-attach query parameters if they existed
        if parsed.query:
            final_url += f"?{parsed.query}"

        return cls(urlparse(final_url))

    @property
    def verify_tls(self) -> str | None:
        """Extracts the 'verify' query parameter."""
        q_params = parse_qs(self.query)
        return q_params.get('verify', [None])[0]

    def get_clean_service_url(self) -> str:
        """Returns the service URL without the custom query params (like ?verify=)."""
        # _replace returns a new instance of the class with the field updated.
        # .geturl() reassembles the parts back into a string.
        return self._replace(query="").geturl()

    def ingress(self, domain: Domain) -> ConfigIngress:
        """Generates the full Cloudflare Ingress dictionary."""
        if domain.port:
            raise ValueError("Domain must not include port number.")
        if not domain.hostname:
            raise ValueError(f"Domain must have hostname! domain:{domain}")

        # 1. Base Config
        config: ConfigIngress = {
            "hostname": domain.hostname,  # type: ignore
            "service": self.get_clean_service_url(),
        }
        if domain.path and domain.path != "/":
            config["path"] = domain.path

        # 2. Origin Request Logic (The Tri-State)
        origin_request: ConfigIngressOriginRequest = {}
        # Only apply TLS settings for HTTPS or Encrypted Sockets
        if self.scheme in ["https", "unix+tls"]:

            # A. Explicit Domain Override (?verify=api.com)
            if self.verify_tls and self.verify_tls.lower() not in ["true", "false"]:
                origin_request["origin_server_name"] = self.verify_tls
                origin_request["http_host_header"] = self.verify_tls

            # B. Explicit Disable (?verify=false)
            elif self.verify_tls and self.verify_tls.lower() == "false":
                origin_request["no_tls_verify"] = True

            # C. Explicit Enable (?verify=true) -> Do nothing (Default)
            elif self.verify_tls and self.verify_tls.lower() == "true":
                pass

            # D. Smart Default (Locals) -> Disable Verify
            # Note: We check hostname for standard URLs, or scheme for unix+tls
            is_local = self.hostname in ["localhost", "127.0.0.1", "::1"]
            if is_local or self.scheme == "unix+tls":
                origin_request["no_tls_verify"] = True

        # 3. Attach if not empty
        if origin_request:
            config["origin_request"] = origin_request

        return config


class Mapping(NamedTuple):
    domain: ParseResult
    service: Service

    @classmethod
    def from_pair(cls, domain: str, service: str) -> Mapping:
        parsed_domain = urlparse(domain)
        if not parsed_domain.scheme:
            parsed_domain = urlparse(f"http://{domain}")

        service_x = Service.autocomplete_from_str(service)
        return cls(parsed_domain, service_x)

    @classmethod
    def from_str(cls, pair: str) -> Mapping:
        """
        Splits 'domain=target' string safely.
        Example: "app.com=localhost:8000" -> ("app.com", "localhost:8000")
        """
        try:
            domain_str, service_str = pair.split("=", 1)
            return cls.from_pair(domain_str, service_str)
        except ValueError:
            raise ValueError(f"Invalid mapping '{pair}'. Expected format 'domain.com=target_url'")
