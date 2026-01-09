from datetime import datetime
from typing import Any, Literal, Self

import aiohttp
from beartype import beartype
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

    # secret: SecretStr

    # @cached_property
    # def token(self):
    #     token_data = {
    #         "a": self.account_id,
    #         "t": self.id,
    #         "s": self.secret.get_secret_value()
    #     }
    #
    #     # 1. Serialize to Minified JSON Bytes (removes whitespace)
    #     text_bytes = json.dumps(token_data, separators=(',', ':')).encode("utf-8")
    #     # 2. Encode to Base64 using direct C call (newline=False skips stripping step)
    #     base64bytes = binascii.b2a_base64(text_bytes, newline=False)
    #     # 3. Decode back to ASCII string for Pydantic
    #     return SecretStr(base64bytes.decode("ascii"))

    @classmethod
    def from_cloudflare_response(cls, response_json: dict[str, Any]) -> Self:
        """
        Custom factory method to parse the nested Cloudflare API response
        into this flat model.
        """
        # result = data.get("result", {})
        # credentials = result.get("credentials_file", {})
        result = response_json["result"]
        credentials = result["credentials_file"]

        return cls(
            id=result["id"],
            name=result["name"],
            account_id=result["account_tag"],
            # Pydantic will automatically parse the ISO 8601 string to a datetime object
            created_at=result["created_at"],
            token=result["token"],
            # We look into the nested credentials_file for the secret
            # secret=credentials["TunnelSecret"],
        )

    def build_dns_record(self, domain: Domain) -> record_batch_params.CNAMERecordParam:
        return record_batch_params.CNAMERecordParam(
            name=domain,
            type="CNAME",
            content=f"{self.id}{consts.cfargotunnel}",
            proxied=True,
            comment=consts.api_managed_tag,
        )


# class AppSettings(BaseSettings):
#     # Pydantic sees "model_config" and applies these rules
#     model_config = SettingsConfigDict(env_prefix="APP_")
#
#     api_key: str
# CLOUDFLARE_API_TOKEN

# def _generate_token(account_id: str, tunnel_id: str, tunnel_secret: SecretStr) -> SecretStr:
#     """
#     Generates a base64 encoded Cloudflare Tunnel Token.
#     Optimized for zero overhead: Minified JSON + Direct C-level Base64.
#     """
#     token_data = {
#         "a": account_id,
#         "t": tunnel_id,
#         "s": tunnel_secret.get_secret_value()
#     }
#
#     # 1. Serialize to Minified JSON Bytes (removes whitespace)
#     text_bytes = json.dumps(token_data, separators=(',', ':')).encode("utf-8")
#     # 2. Encode to Base64 using direct C call (newline=False skips stripping step)
#     base64bytes = binascii.b2a_base64(text_bytes, newline=False)
#     # 3. Decode back to ASCII string for Pydantic
#     return SecretStr(base64bytes.decode("ascii"))


@beartype
async def create_tunnel(
        api_token: str,
        account_id: str,
        tunnel_name: str,
        config_src: Literal["cloudflare", "local"] = "cloudflare",
        metadata: dict[str, Any] | None = None
) -> CustomTunnel:
    api_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel"
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
        async with session.post(api_url, headers=headers, json=payload) as response:
            response.raise_for_status()

            data = await response.json()
            # logger.debug(f"Tunnel creation response: {data}")
            return CustomTunnel.from_cloudflare_response(data)
