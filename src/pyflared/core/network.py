# For low-level cloudflare requests
from collections.abc import AsyncIterator, Iterable
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Literal, Self, Unpack, Final

from cloudflare import NOT_GIVEN, AsyncCloudflare, BadRequestError, NotGiven
from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import RecordListParams, RecordResponse
from cloudflare.types.zero_trust.tunnels.cloudflared import ConfigurationGetResponse
from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import ConfigIngress, Config
from cloudflare.types.zones import Zone
from loguru import logger
from pydantic import JsonValue

from pyflared.api_sdk.tokenized_tunnel import TokenizedTunnel
from pyflared.shared.console import Pretty
from pyflared.shared.types import RecordBatchParam

tunnel_active_connection_error_code: Final[int] = 1022


# type JsonValue = int | float | str | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
# type JsonDict = dict[str, JsonValue]


class CloudflareRequest:

    def __init__(self, client: AsyncCloudflare | None = None) -> None:
        if client:
            self._stack: AsyncExitStack | None = None
            self.client: AsyncCloudflare = client
        else:
            self._stack = AsyncExitStack()
            self.client = AsyncCloudflare()

    async def __aenter__(self) -> Self:
        if self._stack:
            _ = await self._stack.enter_async_context(self.client)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None,
                        traceback: TracebackType | None, ) -> None:
        if self._stack:
            _ = await self._stack.__aexit__(exc_type, exc_val, traceback)

    def tokenized_client(self, token: str) -> AsyncCloudflare:
        return self.client.with_options(api_token=token)

    async def zones_list(
            self, token: str,
            status: Literal["initializing", "pending", "active", "moved"] | NotGiven = "active",
    ) -> AsyncIterator[Zone]:
        async for zone in self.client.with_options(api_token=token).zones.list(status=status):
            yield zone

    async def dns_list(self, token: str, **kwargs: Unpack[RecordListParams]) -> AsyncIterator[RecordResponse]:
        async for record in self.client.with_options(api_token=token).dns.records.list(**kwargs):
            yield record

    # @copy_cf_signature(CloudflaredResource.list)
    # def list_tunnels(self, token: str, *args: Any, **kwargs: Any):
    #     # Your IDE perfectly maps: (self, token: str, *, account_id: str, ...)
    #     return (
    #         self.client.with_options(api_token=token)
    #         .zero_trust.tunnels.cloudflared.list(*args, **kwargs)
    #     )
    # list_tunnels = CFMethod(CloudflaredResource.list)

    # async def dns_edit(self, token: str, zone_id: ZoneId,
    #                    deletes: Iterable[record_batch_params.Delete] | None = None,
    #                    create: Iterable[record_batch_params.Post] | None = None,
    #                    replace: Iterable[record_batch_params.BatchPutParam] | None = None
    #                    ):
    #     # Deletes, Patches(fix), Puts(replace whole), Posts(create)
    #
    #     if create or deletes:
    #         if result := await self.client.with_options(api_token=token).dns.records.batch(
    #                 zone_id=zone_id, posts=create or [], deletes=deletes or [], puts=replace or []):
    #             logger.debug(f"Batch creation result: {Pretty(result.model_dump())}")
    #             return result
    #         else:
    #             raise Exception("Batch request returned empty!")
    #     else:
    #         raise Exception("No input provided!")

    async def dns_edit(self, token: str, batch: RecordBatchParam):
        # Deletes, Patches(fix), Puts(replace whole), Posts(create)
        if not batch:
            raise Exception("No input provided!")
        if result := await self.client.with_options(api_token=token).dns.records.batch(
                zone_id=batch.zone.id, posts=batch.creates, deletes=batch.deletes,
                puts=batch.replace, patches=batch.edit):
            logger.debug(f"Batch creation result: {Pretty(result.model_dump())}")
            return result
        else:
            raise Exception("Batch request returned empty!")

    async def tunnels_list(
            self, token: str, *, account_id: str, name: str | None = None) -> AsyncIterator[CloudflareTunnel]:
        async for tunnel in self.client.with_options(api_token=token).zero_trust.tunnels.cloudflared.list(
                account_id=account_id, is_deleted=False, name=name or NOT_GIVEN):
            yield tunnel  # pyright: ignore[reportReturnType]

    async def create_tunnel(
            self,
            api_token: str,
            account_id: str,
            tunnel_name: str,
            config_src: Literal["cloudflare", "local"] = "cloudflare",
            # metadata: JsonDict | None = None
            metadata: dict[str, Any] | None = None
    ) -> TokenizedTunnel:
        create_tunnel_endpoint = f"accounts/{account_id}/cfd_tunnel"  # SDK handles base URL

        payload: dict[str, JsonValue] = {
            "name": tunnel_name,
            "config_src": config_src
        }

        if metadata:
            payload["metadata"] = metadata

        response = await self.client.with_options(api_token=api_token).post(
            create_tunnel_endpoint,
            body=payload,
            cast_to=dict[str, Any]
        )
        return TokenizedTunnel.from_creation_response(response)

    async def update_tunnel_ingress(
            self, token: str, tunnel_id: str, account_id: str, ingresses: Iterable[ConfigIngress]):
        _ = await self.client.with_options(api_token=token).zero_trust.tunnels.cloudflared.configurations.update(
            tunnel_id=tunnel_id, account_id=account_id, config=Config(ingress=ingresses)
        )

    async def tunnel_configurations(self, token: str, tunnel_id: str,
                                    account_id: str, ) -> ConfigurationGetResponse:
        if configuration := await self.client.with_options(
                api_token=token).zero_trust.tunnels.cloudflared.configurations.get(
            tunnel_id=tunnel_id, account_id=account_id):
            return configuration
        else:
            raise Exception("No configuration found!")

    async def tunnel_token(self, token: str, tunnel_id: str, account_id: str, ):
        return await self.tokenized_client(token).zero_trust.tunnels.cloudflared.token.get(
            tunnel_id=tunnel_id, account_id=account_id)

    async def delete_tunnel(self, token: str, tunnel: CloudflareTunnel | TokenizedTunnel):
        logger.info(f"Deleting orphan tunnel: {tunnel.name}")
        result = await self.client.with_options(api_token=token).zero_trust.tunnels.cloudflared.delete(
            tunnel_id=tunnel.id, account_id=tunnel.account_tag)  # pyright: ignore[reportArgumentType]
        logger.debug(f"Deletion result: {Pretty(result.model_dump())}")

    async def cleanup_tunnel_connection(self, token: str, tunnel: CloudflareTunnel | TokenizedTunnel):
        # This is the binary API equivalent of `cloudflared tunnel cleanup`
        logger.info(f"Cleaning up ghost connections: {tunnel.name}")
        result = await self.client.with_options(api_token=token).zero_trust.tunnels.cloudflared.connections.delete(
            tunnel_id=tunnel.id, account_id=tunnel.account_tag)  # pyright: ignore[reportArgumentType]
        logger.debug("Cleanup result: {}", Pretty(result))

    async def force_delete_tunnel(self, token: str, tunnel: CloudflareTunnel | TokenizedTunnel):
        try:
            await self.delete_tunnel(token, tunnel)
        except BadRequestError as e:
            error_codes = (err.code for err in e.errors)

            if tunnel_active_connection_error_code in error_codes:
                await self.cleanup_tunnel_connection(token, tunnel)
                # retry
                await self.delete_tunnel(token, tunnel)
            else:
                # Re-raise if it's a different error (e.g., auth, permissions)
                raise
