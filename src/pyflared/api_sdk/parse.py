from __future__ import annotations

import re
from functools import cached_property
from typing import Final, NamedTuple
from urllib.parse import ParseResult, parse_qs, urlparse

from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import (
    ConfigIngress,
    ConfigIngressOriginRequest,
)

type Domain = ParseResult

# Cloudflare supported schemes
CLOUDFLARE_SUPPORTED_SCHEMES: Final[frozenset[str]] = frozenset({
    "http", "https", "unix", "tcp", "ssh", "rdp", "unix+tls", "smb", "ws", "wss"
})

# Special Cloudflare services that don't require a URL
CLOUDFLARE_SPECIAL_SERVICES: Final[frozenset[str]] = frozenset({
    "hello_world", "hello-world", "bastion", "socks5"
})

# HTTP status service pattern: http_status:<code>
CLOUDFLARE_HTTP_STATUS_RE: Final[re.Pattern[str]] = re.compile(r"^http_status:\d+$")

# Local hostnames for TLS verification defaults
LOCAL_HOSTNAMES: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})

# Local schemes (unix sockets)
LOCAL_SCHEMES: Final[frozenset[str]] = frozenset({"unix", "unix+tls"})

# Port to scheme mapping
PORT_TO_SCHEMES: Final[dict[int, str]] = {
    80: "http",
    443: "https",
    22: "ssh",
    3389: "rdp",
    3306: "tcp",
    5432: "tcp",
    6379: "tcp",
    27017: "tcp",
}


def _is_special_cloudflare_service(url: str) -> bool:
    """Check if URL is a special Cloudflare service or http_status pattern.

    Args:
        url: The URL string to check

    Returns:
        True if the URL is a special service, False otherwise
        
    Examples:
        >>> _is_special_cloudflare_service("hello_world")
        True
        >>> _is_special_cloudflare_service("bastion")
        True
        >>> _is_special_cloudflare_service("http_status:404")
        True
        >>> _is_special_cloudflare_service("localhost:8000")
        False
    """
    return url.lower() in CLOUDFLARE_SPECIAL_SERVICES or bool(CLOUDFLARE_HTTP_STATUS_RE.match(url))


def _looks_like_port(value: str) -> bool:
    if not value.isdigit():
        return False
    port = int(value)
    return 1 <= port <= 65535


def _extract_port_from_path(path: str) -> int | None:
    """Extract port number from a path if it starts with a port.

    Args:
        path: Path string that might start with a port

    Returns:
        Port number if valid, None otherwise
        
    Examples:
        >>> _extract_port_from_path("27017")
        27017
        >>> _extract_port_from_path("27017/path")
        27017
        >>> _extract_port_from_path("/var/run")
        None
    """
    first_segment = path.lstrip("/").split("/")[0]
    if _looks_like_port(first_segment):
        return int(first_segment)
    return None


class Service(ParseResult):
    """Extended ParseResult that can self-verify SSL settings and generate Ingress Config."""

    def __new__(cls, parsed: ParseResult):
        return super().__new__(cls, *parsed)

    @classmethod
    def from_str(cls, url: str) -> Service:
        """Normalizes a lazy input string into a strict ParseResult.

        Handles various input formats:
        - '8000' -> 'http://localhost:8000'
        - 'localhost:8000' -> 'http://localhost:8000'
        - 'unix:/path' -> 'unix:/path'
        - 'app.com' -> 'http://app.com'
        - etc.

        Args:
            url: Input URL string to normalize

        Returns:
            Normalized Service instance
        """

        parsed = urlparse(url)

        # Best case, the user already provided a valid URL
        if _is_special_cloudflare_service(url) or parsed.scheme in CLOUDFLARE_SUPPORTED_SCHEMES:
            return cls(parsed)

        # Case A: Network Location (host or port found)
        # Examples:
        #   "8000" -> 'http://localhost:8000'
        #   "localhost:3000" -> 'http://localhost:3000'
        #   "my-db:27017" -> 'tcp://my-db:27017'
        #   "8000/api" -> 'http://localhost:8000/api'
        if port := _extract_port_from_path(parsed.path):
            scheme = PORT_TO_SCHEMES.get(port, "http")
            assert not parsed.netloc  # For now, I'm expecting netloc to be empty, till I find a contrary example
            netloc = parsed.scheme or "localhost"
            return cls(urlparse(f"{scheme}://{netloc}:{parsed.path}")._replace(query=parsed.query))

        # Let's say anything else is a Unix Socket (For now, till I find a contrary example)
        # Case B: Unix Socket (absolute path)
        # Examples:
        #   "/var/run/app.sock" -> 'unix:/var/run/app.sock'
        #   "/tmp/redis.sock" -> 'unix:/tmp/redis.sock'
        return cls(urlparse(f"unix:{parsed.path}")._replace(query=parsed.query))

    @cached_property
    def verify_tls(self) -> str | None:
        """TLS verification parameter from query (?verify_tls)."""
        q_params = parse_qs(self.query)
        return q_params.get("verify_tls", [None])[-1]

    @cached_property
    def host_header(self) -> str | None:
        """Custom HTTP Host header from query (?host_header)."""
        q_params = parse_qs(self.query)
        return q_params.get("host_header", [None])[-1]

    @cached_property
    def is_local(self) -> bool:
        """Check if the URL points to a local resource.

        Returns:
            True if the hostname is localhost-like or using unix sockets
            
        Examples:
            >>> service = Service.from_str("localhost:8000")
            >>> service.is_local
            True
            >>> service = Service.from_str("unix:/var/run/app.sock")
            >>> service.is_local
            True
            >>> service = Service.from_str("example.com")
            >>> service.is_local
            False
        """
        return self.hostname in LOCAL_HOSTNAMES or self.scheme in LOCAL_SCHEMES

    @cached_property
    def service_url(self) -> str:
        """Return the service URL without custom query params (like ?verify=).

        Returns:
            Clean service URL string
        """
        return self._replace(query="").geturl()

    @cached_property
    def origin_config(self) -> ConfigIngressOriginRequest:
        origin_request: ConfigIngressOriginRequest = {}

        # Only apply TLS settings for HTTPS or Encrypted Sockets
        if self.scheme in {"https", "unix+tls"}:
            if self.verify_tls is not None:
                verify_lower = self.verify_tls.lower()  # Cache it!

                if verify_lower not in {"true", "false"}:
                    # A. Explicit Domain Override (?verify=api.com)
                    origin_request["origin_server_name"] = self.verify_tls
                    origin_request["http_host_header"] = self.host_header or self.verify_tls
                elif verify_lower == "false":
                    # B. Explicit Disable
                    origin_request["no_tls_verify"] = True
                # C. Explicit/Force Enable (?verify=true) -> Do nothing (enabled by Default)
            elif self.is_local:
                # D. Smart Default (Locals)
                origin_request["no_tls_verify"] = True

        return origin_request

    def ingress(self, domain: Domain) -> ConfigIngress:
        """Generate the full Cloudflare Ingress configuration.

        Args:
            domain: Parsed domain information

        Returns:
            ConfigIngress dictionary

        Raises:
            ValueError: If domain includes a port or lacks a hostname
        """
        # We dont care about domain scheme
        if domain.port:
            raise ValueError("Domain must not include port number.")
        if domain.query:
            raise ValueError(f"Domain must not include query parameters! domain:{domain}")
        if not domain.hostname:
            raise ValueError(f"Domain must have hostname! domain:{domain}")

        # 1. Base Config
        config: ConfigIngress = {
            "hostname": domain.hostname,  # type: ignore
            "service": self.service_url,
        }

        if domain.path and domain.path != "/":
            config["path"] = domain.path

        # 3. Attach if not empty
        if self.origin_config:
            config["origin_request"] = self.origin_config

        return config


class Mapping(NamedTuple):
    """Represents a mapping between a domain and a service."""

    domain: ParseResult
    service: Service

    @classmethod
    def from_pair(cls, domain: str, service: str) -> Mapping:
        """Create a Mapping from domain and service strings.

        Args:
            domain: Domain string
            service: Service string

        Returns:
            Mapping instance
        """
        parsed_domain = urlparse(domain)
        if not parsed_domain.scheme:
            # The same file hack, scheme for domain will be thrown away anyway
            parsed_domain = urlparse(f"file://{domain}")

        service_x = Service.from_str(service)
        return cls(parsed_domain, service_x)

    @classmethod
    def from_str(cls, pair: str) -> Mapping:
        """Create a Mapping from a domain=service string.

        Args:
            pair: String in format "domain.com=target_url"

        Returns:
            Mapping instance

        Raises:
            ValueError: If the string doesn't contain exactly one '=' separator

        Example:
            >>> Mapping.from_str("app.com=localhost:8000")
            Mapping(domain='app.com', service='localhost:8000')
        """
        if "=" not in pair:
            raise ValueError(f"Invalid mapping '{pair}'. Expected format 'domain.com=target_url'")

        domain_str, service_str = pair.split("=", 1)
        return cls.from_pair(domain_str, service_str)

    def ingress(self) -> ConfigIngress:
        """Generate Cloudflare Ingress config for this mapping.

        Returns:
            ConfigIngress dictionary
        """
        return self.service.ingress(self.domain)
