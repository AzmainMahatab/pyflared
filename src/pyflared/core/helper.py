import re
import socket
from collections.abc import Awaitable, Iterable
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Callable

from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import RecordResponse, RecordBatchResponse

from pyflared.api_sdk.tokenized_tunnel import TokenizedTunnel
from pyflared.core.model import ZoneEntry
from pyflared.shared import consts
from pyflared.utils.type_check import is_of_type


class All:
    pass


ALL = All()
temp_tags = (consts.api_managed_tag, consts.ephemeral)


def auto_tunnel_name() -> str:
    """
    Generates a readable, consistent tunnel name.
    Format: hostname_YYYY-MM-DD_HH-MM-SS
    Example: 'macbook-pro_2026-01-09_16-30-05'
    """
    # 1. Get Hostname & Clean it
    # We split by '.' to handle FQDNs (e.g., 'server01.us-east.prod' -> 'server01')
    raw_host = socket.gethostname().split('.')[0]

    # Remove special chars to ensure CLI/API compatibility, keep underscores/hyphens
    clean_host = re.sub(r'[^a-zA-Z0-9_-]', '-', raw_host).lower()

    # 2. Get UTC Time (Consistent across all timezones)
    # Using specific format: Date and Time separated by underscore
    now_utc = datetime.now(UTC)
    human_timestamp = now_utc.strftime("%Y-%m-%d_%H-%M-%S")

    return f"{clean_host}_{human_timestamp}"


def get_tunnel_id(record: RecordResponse) -> str | None:
    return record.content.removesuffix(  # pyright: ignore[reportOptionalMemberAccess]
        consts.cfargotunnel) if record.content.endswith(  # pyright: ignore[reportOptionalMemberAccess]
        consts.cfargotunnel) else None


def tunnel_is_down(tunnel: CloudflareTunnel) -> bool:
    return tunnel.status in ("inactive", "down")


def tunnel_has_tags(tunnel: CloudflareTunnel, tags: Iterable[str]) -> bool:
    return bool(
        isinstance(metadata := tunnel.metadata, dict)
        and is_of_type(found_tags := metadata.get("tags"), list)
        and set(tags).issubset(found_tags)
    )


def dns_has_tags(record: RecordResponse, tags: Iterable[str]) -> bool:
    required_tags: set[str] = set(tags)

    # Replace commas with spaces, then split by whitespace
    comment: str = record.comment or ""
    comment_tags: set[str] = set(comment.replace(",", " ").split())

    return required_tags.issubset(comment_tags)

    # def tunnel_has_tags(tunnel: CloudflareTunnel, tags: Iterable[str]) -> bool:
    #     return bool(
    #         isinstance(found_tags := tunnel.metadata.get(consts.tags), list)
    #         and set(tags).issubset(found_tags)
    #     )

    # def tunnel_has_tags(tunnel: CloudflareTunnel, tags: Iterable[str]) -> bool:
    #     return bool(
    #         (found_tags := tunnel.metadata.get(consts.tags))
    #         and set(tags).issubset(found_tags)
    #     )

    # is_of_type(metadata := tunnel.metadata, dict[str, Any])
    # and is_of_type(found_tags := metadata.get(consts.tags), list[str])
    # and set(tags).issubset(found_tags)

    # def is_orphan(tunnel: CloudflareTunnel) -> bool:
    #     # has tag, inactive + time, down
    #     # now = datetime.now(timezone.utc)
    #     # threshold = now - timedelta(seconds=5)
    #     # return tunnel.metadata.get(_tag) and (
    #     #         (tunnel.status == "inactive" and tunnel.created_at < threshold) or (
    #     #         tunnel.status == "down" and tunnel.conns_inactive_at and tunnel.conns_inactive_at < threshold)
    #     # )
    #     # Must have our tag + inactive or down (0 or -1 connections)
    #     return is_ours(tunnel) and tunnel.status in ("inactive", "down")
    #
    #
    # @overload
    # def is_ours(record: RecordResponse) -> bool: ...
    #
    #
    # @overload
    # def is_ours(tunnel: CloudflareTunnel) -> bool: ...
    #
    #
    # def is_ours(obj: object) -> bool:  # pyright: ignore[reportInconsistentOverload]
    #     match obj:
    #         case CNAMERecord() as record:
    #             return consts.api_managed_tag in (record.comment or "")
    #         case CloudflareTunnel() as tunnel:
    #             # Explicitly cast to bool in case .get() returns None or a non-bool value
    #             return bool(tunnel.metadata.get(consts.api_managed_tag))
    #         case _:
    #             return False


@dataclass
class ConfiguredTunnel:
    tunnel: TokenizedTunnel
    config: list[tuple[ZoneEntry, RecordBatchResponse]]
    clean_up: Callable[[], Awaitable[None]]

    @property
    def tunnel_token(self):
        return self.tunnel.tunnel_token
