from datetime import datetime
from typing import Any, Self

from cloudflare.types.dns import record_batch_params
from pydantic import BaseModel, SecretStr

from pyflared import consts
from pyflared.shared.types import Domain, TunnelId


class CustomTunnel(BaseModel):
    """
    A flat Pydantic model representing the essential Tunnel configuration.
    """
    id: TunnelId
    name: str
    account_id: str
    created_at: datetime
    token: SecretStr

    @classmethod
    def from_cloudflare_response(cls, response_json: dict[str, Any]) -> Self:
        """
        Custom factory method to parse the nested Cloudflare API response
        into this flat model.
        """
        result = response_json["result"]

        return cls(
            id=result["id"],
            name=result["name"],
            account_id=result["account_tag"],
            # Pydantic will automatically parse the ISO 8601 string to a datetime object
            created_at=result["created_at"],
            token=result["token"],
        )

    def build_dns_record(self, domain: Domain) -> record_batch_params.CNAMERecordParam:
        return record_batch_params.CNAMERecordParam(
            name=domain,
            type="CNAME",
            content=f"{self.id}{consts.cfargotunnel}",
            proxied=True,
            comment=consts.api_managed_tag,
        )
