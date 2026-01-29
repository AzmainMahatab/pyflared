from datetime import datetime
from typing import Self, Any

from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import record_batch_params
from pydantic import BaseModel, SecretStr

from pyflared.shared import consts
from pyflared.shared.types import Cname, TunnelId


class TokenizedTunnel(BaseModel):
    """
    A flat Pydantic model representing the essential Tunnel configuration.
    """
    id: TunnelId
    name: str
    account_id: str
    created_at: datetime
    tunnel_token: SecretStr

    # api_token: SecretStr

    @property
    def account_tag(self) -> str:
        return self.account_id

    @classmethod
    def from_creation_response(cls, response_json: dict[str, Any]) -> Self:
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
            tunnel_token=result["token"],
            # api_token=SecretStr(api_token),
        )

    @classmethod
    def from_tunnel(cls, cloudflare_tunnel: CloudflareTunnel) -> Self:
        ...

    def build_dns_record(self, subdomain: Cname, epimeral: bool = False) -> record_batch_params.CNAMERecordParam:
        comment = f"{consts.api_managed_tag},{consts.ephemeral if epimeral else ""}"

        return record_batch_params.CNAMERecordParam(
            name=subdomain,
            type="CNAME",
            content=f"{self.id}{consts.cfargotunnel}",
            proxied=True,
            comment=comment,
        )
