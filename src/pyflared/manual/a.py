import aiohttp
import asyncio
import os
from typing import Any, Dict, Optional

from pydantic import BaseModel


class Address(BaseModel):
    city: str
    zipcode: str


class CFClient:
    def __init__(self, token: str):
        self.token = token

    async def create_cloudflare_tunnel(
            self,
            account_id: str,
            tunnel_name: str = "api-tunnel",
    ) -> Dict[str, Any]:
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        payload = {
            "name": tunnel_name,
            "config_src": "cloudflare"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                # Raise an exception for 4xx/5xx status codes
                response.raise_for_status()

                # Return parsed JSON
                return await response.json()
