import re
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated
import validators

import typer
from pydantic import BaseModel, Field, computed_field, model_validator, HttpUrl, BeforeValidator, AfterValidator


def validate_domain_or_ip(v: str) -> str:
    # 1. Check if it's a valid IP Address (IPv4 or IPv6)
    # We use the standard library 'ipaddress' because it is faster and built-in.
    try:
        ip_address(v)
        return v  # It is a valid IP, we are done.
    except ValueError:
        pass  # Not an IP, fall through to domain check.

    # 2. Check if it's a valid Public Domain
    # validators.domain() strictly enforces TLDs (dots), so "23w" or "localhost" will fail.
    if validators.domain(v) is True:
        return v

    raise ValueError(f"Invalid Public Domain or IP Address: '{v}'")


HostName = Annotated[str, AfterValidator(validate_domain_or_ip)]


class SSHConfig(BaseModel):
    # Alias is Optional (Input-wise)
    alias: str | None = Field(default=None, exclude=True)

    # Hostname is the ONLY mandatory input
    # CRITICAL: Don't use Field(...) in Annotated with typer.Argument - causes Ellipsis issues in wheels  
    # We use typer.Argument to make it required for CLI, but provide a default_factory for Pydantic
    hostname: Annotated[
        HostName,
        Field(serialization_alias="HostName"),
        typer.Argument(help="Hostname: RFC 1123 + IPv4/IPv6 compatible")
    ]

    user: str | None = Field(default=None, serialization_alias="User")
    identity_file: Path | None = Field(default=None, serialization_alias="IdentityFile")

    port: int | None = Field(default=None, serialization_alias="Port")

    # If alias is missing, mirror the hostname
    @model_validator(mode='after')
    def set_default_alias(self):
        # If the user didn't provide an alias, use the hostname
        if self.alias is None:
            self.alias = self.hostname
        return self

    @computed_field(alias="ProxyCommand")
    def proxy_command(self) -> str:
        # return f"{pyflared._commands.get_path()} access ssh --hostname %h"
        return "cloudflared access ssh --hostname %h"

    def config_text(self) -> str:
        # Note: self.alias is guaranteed to have a value now because of the validator
        data = self.model_dump(by_alias=True, exclude_none=True)
        return (f"Host {self.alias}\n" +
                "\n".join(
                    f"    {k} {v}" for k, v in data.items()
                ) + "\n")

    @property
    def filename(self) -> str:
        """
        Generates a safe filename (e.g., for IPv6 or messy aliases).
        Input: 2001:db8::1
        Output: 2001_db8__1.conf
        """
        # Get the alias (guaranteed to be set by the validator below)
        raw_name = self.alias

        # Aggressive Sanitization:
        # Replace ANYTHING that isn't a Letter, Number, Dot, Dash, or Underscore.
        # This catches Colons (:), Spaces, Slashes, etc.
        safe_name = re.sub(r'[^\w.-]', '_', raw_name)
        return f"{safe_name}.conf"
