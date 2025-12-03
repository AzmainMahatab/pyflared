from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

import aiohttp
from cloudflare.types.dns import record_batch_params
from pydantic import BaseModel, SecretStr

from pyflared import consts
from pyflared.typealias import Domain


class CreatedTunnel(BaseModel):
    """
    A flat Pydantic model representing the essential Tunnel configuration.
    """
    tunnel_id: UUID
    tunnel_name: str
    account_id: str
    created_at: datetime
    secret: SecretStr

    @classmethod
    def from_cloudflare_response(cls, data: dict[str, Any]) -> Self:
        """
        Custom factory method to parse the nested Cloudflare API response
        into this flat model.
        """
        # result = data.get("result", {})
        # credentials = result.get("credentials_file", {})
        result = data["result"]
        credentials = result["credentials_file"]

        return cls(
            tunnel_id=result["id"],
            tunnel_name=result["name"],
            account_id=result["account_tag"],
            # Pydantic will automatically parse the ISO 8601 string to a datetime object
            created_at=result["created_at"],
            # We look into the nested credentials_file for the secret
            secret=credentials["TunnelSecret"]
        )

    def dns_record(self, domain: Domain) -> record_batch_params.CNAMERecordParam:
        return record_batch_params.CNAMERecordParam(
            name=domain,
            type="CNAME",
            content=f"{self.tunnel_id}{consts.cfargotunnel}",
            proxied=True,
            comment=consts.tag,
        )


async def create_tunnel(
        api_token: str,
        account_id: str,
        tunnel_name: str,
        config_src: Literal["cloudflare", "local"] = "cloudflare",
        metadata: dict[str, Any] | None = None
) -> CreatedTunnel:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel"

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {
        "name": tunnel_name,
        "config_src": config_src
    }

    if metadata:
        payload["metadata"] = metadata

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            response.raise_for_status()

            json = await response.json()
            return CreatedTunnel.from_cloudflare_response(json)
