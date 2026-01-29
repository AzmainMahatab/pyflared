import asyncio
from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from contextlib import AsyncExitStack
from functools import partial
from types import TracebackType
from typing import Self

import tldextract
from cloudflare import PermissionDeniedError
from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import batch_put_param, record_batch_params, CNAMERecordParam, \
    RecordBatchResponse
from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import ConfigIngress
from loguru import logger
from pydantic import SecretStr
from sqlmodel import select, col
from sqlmodel.ext.asyncio.session import AsyncSession

from pyflared.api_sdk.ingress import fix_ingress_order
from pyflared.api_sdk.parse import Mapping
from pyflared.api_sdk.tokenized_tunnel import TokenizedTunnel
from pyflared.core.helper import auto_tunnel_name, get_tunnel_id, ConfiguredTunnel, tunnel_has_tags, \
    tunnel_is_down, dns_has_tags, All, ALL, temp_tags
from pyflared.core.model import ZoneEntry, TokenLookupLink, Token
from pyflared.core.network import CloudflareRequest
from pyflared.core.repository import TokenHint, save_trial, add_token, engine, \
    remove_tokens, ensure_tables, invalidate_cache, envar_token
from pyflared.shared import consts
from pyflared.shared.console import Pretty
from pyflared.shared.types import RecordBatchParam, delify_response
from pyflared.utils.run_failover import run_failover
from pyflared.utils.asyncio.async_Iterable import yield_from_async
from pyflared.utils.set import set_remove

type DomainSubDomainMapping = defaultdict[str, set[str]]  # Domain -> subdomains

_extract = tldextract.TLDExtract(include_psl_private_domains=True)


def domain_from_subdomain(cname: str) -> str:
    return _extract(cname).top_domain_under_public_suffix


class TunnelService:
    def __init__(self, cloudflare_request: CloudflareRequest | None = None) -> None:
        self.token_hint: TokenHint = TokenHint()

        if cloudflare_request:
            self._stack: AsyncExitStack | None = None
            self.cloudflare_request: CloudflareRequest = cloudflare_request
        else:
            self._stack = AsyncExitStack()
            self.cloudflare_request = CloudflareRequest()

    async def refresh_tokens(self):
        await self.token_hint.refresh()

    async def __aenter__(self) -> Self:
        if self._stack:
            _ = await self._stack.enter_async_context(self.cloudflare_request)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None,
                        traceback: TracebackType | None, ) -> None:
        if self._stack:
            _ = await self._stack.__aexit__(exc_type, exc_val, traceback)

    @yield_from_async
    def tunnel_list(self, account_id: str, name: str | None = None):
        tokens = self.token_hint.priority_tokens(account_id)
        runner = partial(self.cloudflare_request.tunnels_list, account_id=account_id, name=name)
        return run_failover(runner, tokens)

    @yield_from_async
    def dns_list(self, zone_id: str):
        tokens = self.token_hint.priority_tokens(zone_id)
        runner = partial(self.cloudflare_request.dns_list, zone_id=zone_id)
        return run_failover(runner, tokens)

    async def dns_edit(self, batch_param: RecordBatchParam):
        logger.debug(f"DNS records: {Pretty(batch_param)}")
        key = batch_param.zone.name
        tokens = await self.token_hint.priority_tokens(key)

        runner = partial(
            self.cloudflare_request.dns_edit, batch=batch_param)
        on_complete = partial(
            save_trial, key=key)

        return await run_failover(
            runner, tokens, on_complete=on_complete)

    async def create_tunnel(
            self, primary_zone: ZoneEntry, tunnel_name: str | None = None) -> TokenizedTunnel:
        tags = [consts.api_managed_tag]
        if not tunnel_name:
            tags.append(consts.ephemeral)

        tunnel_name = tunnel_name or auto_tunnel_name()
        aid = primary_zone.account_id

        tokens = self.token_hint.priority_tokens(aid, primary_zone.name)
        runner = partial(
            self.cloudflare_request.create_tunnel, account_id=aid, tunnel_name=tunnel_name,
            metadata={consts.tags: tags}, )
        on_complete = partial(save_trial, key=aid)
        return await run_failover(runner, tokens, on_complete=on_complete)

    async def tunnel_ingress(self, tunnel: CloudflareTunnel):
        tokens = self.token_hint.priority_tokens(tunnel.account_tag)
        runner = partial(self.cloudflare_request.tunnel_configurations,
                         account_id=tunnel.account_tag, tunnel_id=tunnel.id, )  # pyright: ignore[reportArgumentType]
        on_complete = partial(save_trial, key=tunnel.account_tag)  # pyright: ignore[reportArgumentType]
        config = await run_failover(runner, tokens, on_complete=on_complete)
        return (config.config and config.config.ingress) or []

    async def update_tunnel_ingress(
            self, tunnel: TokenizedTunnel, ingresses: Iterable[ConfigIngress]):
        tokens = self.token_hint.priority_tokens(tunnel.account_id)

        runner = partial(self.cloudflare_request.update_tunnel_ingress, tunnel_id=tunnel.id,
                         account_id=tunnel.account_id, ingresses=ingresses)
        on_complete = partial(save_trial, key=tunnel.account_id)

        await run_failover(runner, tokens, on_complete=on_complete)

    async def tunnel_token(self, tunnel: CloudflareTunnel):
        tid: str = tunnel.id  # pyright: ignore[reportAssignmentType]
        aid: str = tunnel.account_tag  # pyright: ignore[reportAssignmentType]

        tokens = self.token_hint.priority_tokens(aid)
        runner = partial(self.cloudflare_request.tunnel_token, tunnel_id=tid, account_id=aid)
        on_complete = partial(save_trial, key=aid)
        return await run_failover(runner, tokens, on_complete=on_complete)

    async def force_delete_tunnel(self, tunnel: CloudflareTunnel | TokenizedTunnel):
        aid = tunnel.account_tag

        tokens = self.token_hint.priority_tokens(aid)
        runner = partial(self.cloudflare_request.force_delete_tunnel, tunnel=tunnel)
        oncomplete = partial(save_trial,
                             key=aid)  # pyright: ignore[reportArgumentType]
        await run_failover(runner, tokens, on_complete=oncomplete)

    async def sync_db(self):  # Update from API
        zones = list[ZoneEntry]()

        # links: LinkMemory = {}
        async def sync_zones_from_token(token: Token, save_token: bool = False):
            if save_token:
                _ = await add_token(token)
                await self.token_hint.refresh()

            # links = await self.link_memory
            # zone_memory = await self.zone_memory

            async with AsyncSession(engine, expire_on_commit=False) as session:
                try:
                    # get zones
                    async for zone in self.cloudflare_request.zones_list(token.value):
                        # save zone info
                        ze = ZoneEntry.from_response(zone)
                        domain = ze.name

                        session.add(ze)
                        zones.append(ze)

                        lookup_link = TokenLookupLink(token_value=token.value, search_key=domain)
                        session.add(lookup_link)
                        # links[token].add(domain) # We Are NOT saving any links here! thats because we here we know token has edit power, it doesnt say anything about if we can edit or not, maybe if we add scoring system in future, ie, read 1 and write 2 we can un-comment it and save it then

                except PermissionDeniedError as e:
                    err_codes = [error.code for error in e.errors]
                    if 9109 in err_codes:
                        logger.warning(f"Dead token, removing from database, token: {token}")
                        _ = await remove_tokens(token.name)
                    else:
                        raise e  # We have not seen this before, re-raise for analysis

                await session.commit()

        async def body():
            async with asyncio.TaskGroup() as tg:
                if env_token := envar_token():
                    _ = tg.create_task(
                        sync_zones_from_token(env_token, save_token=True))

                await ensure_tables()
                async with AsyncSession(engine) as session:
                    await invalidate_cache(session)
                    await session.commit()

                    statement = select(Token)
                    result = await session.exec(statement)
                    tokens = result.all()

                if not tokens:
                    raise ValueError("No tokens found! Please add tokens using 'pyflared token add")
                for token in tokens:
                    _ = tg.create_task(sync_zones_from_token(token))

        await body()
        return zones

    async def get_zones(self, domains: Collection[str] | None = None) -> Sequence[ZoneEntry]:
        """
        Fetches zone entries from the database, ensuring missing entries are synced.

        Parameters:
        - domains (set[str] | None): A set of specific domain strings to fetch.
          If set to `None`, it syncs the database and returns all available zones.
          Defaults to `None`.
        """
        # 1. Fast Path: Handle the "fetch all" scenario immediately
        if not domains:
            return await self.sync_db()

        # 2. Targeted Fetch Path: Proceed linearly for subsets
        statement = select(ZoneEntry).where(col(ZoneEntry.name).in_(domains))

        async with AsyncSession(engine) as session:
            results = (await session.exec(statement)).all()

            # 3. Success Path: We found everything on the first try
            if len(results) == len(domains):
                return results

            # 4. Fallback Path: Sync missing data and retry
            await session.rollback()
            _ = await self.sync_db()
            zones = (await session.exec(statement)).all()

            # zones = {zone.name: zone for zone in results}

            # 5. Final Validation: Throw clear errors if still missing
            if len(zones) != len(domains):
                found_domains = {zone.name for zone in zones}
                missing_domains = set(domains) - found_domains
                raise ValueError(
                    f"Could not find all domains. Found: {found_domains} | Missing: {missing_domains}"
                )

            return zones


class TunnelManager:
    # tunnel_service: TunnelService = field(default_factory=TunnelService)

    def __init__(self, tunnel_service: TunnelService | None = None) -> None:
        if tunnel_service:
            self._stack: AsyncExitStack | None = None
            self.tunnel_service: TunnelService = tunnel_service
        else:
            self._stack = AsyncExitStack()
            self.tunnel_service = TunnelService()

    async def __aenter__(self) -> Self:
        if self._stack:
            _ = await self._stack.enter_async_context(self.tunnel_service)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None,
                        traceback: TracebackType | None, ) -> None:
        if self._stack:
            _ = await self._stack.__aexit__(exc_type, exc_val, traceback)

    # We won't do any tunnel clean here, as temp tunnel is meant ot be cleaned up on shutdown,
    # if some orphan is created by abrupt shutdown, it can be cleaned up by remove orphans command
    async def _configure_dns(
            self,
            zones: Iterable[ZoneEntry],
            domain_subdomain_mapping: DomainSubDomainMapping | All,
            # None here means everything you find in that zone, useful for cleanup
            tunnel_id: str | None,  # None means we want to delete, not connect to a tunnel
            epimeral: bool,  # when tunnel_id is none, this parameter is ignored
            force: bool = False,  # Typically named and active tunnels are respected, if Ture, it won't respect them
    ):
        # Many zones have the same account, this is to prevent the same account repeat check
        scanned_account = set[str]()
        # These are protected tunnels, we cannot delete them, when force is provided, this is empty, meaning all tunnels will be cleanup
        protected_tunnels = set[str]()

        async def scan_tunnels(aid: str):
            if aid in scanned_account:
                return
            scanned_account.add(aid)

            async with asyncio.TaskGroup() as tg:
                async for tunnel in self.tunnel_service.tunnel_list(aid):
                    if force or (tunnel_is_down(tunnel) and tunnel_has_tags(tunnel, temp_tags)):
                        if not tunnel_id:
                            _ = tg.create_task(self.tunnel_service.force_delete_tunnel(tunnel))
                    else:
                        protected_tunnels.add(tunnel.id)  # pyright: ignore[reportArgumentType]

        responses = list[tuple[ZoneEntry, RecordBatchResponse]]()

        async def set_zone_dns(zone: ZoneEntry):
            zone_domains = domain_subdomain_mapping[zone.name] if not isinstance(domain_subdomain_mapping,
                                                                                 All) else None

            zone_records = RecordBatchParam(zone)

            # comment = f"{consts.api_managed_tag},{consts.ephemeral if epimeral else ""}"
            content = f"{tunnel_id}{consts.cfargotunnel}"

            async for record in self.tunnel_service.dns_list(zone.id):
                if not zone_domains or set_remove(zone_domains, record.name):
                    if tid := get_tunnel_id(record):  # We only touch if it's connected to tunnel
                        if (
                                # dns_has_tags(record, temp_tags) or
                                tid not in protected_tunnels
                        ):
                            if tunnel_id:
                                replace_record = batch_put_param.CNAMERecord(
                                    id=record.id,
                                    name=record.name,
                                    type="CNAME",
                                    content=content,
                                    # comment=comment,
                                    proxied=True,
                                )
                                zone_records.replace.append(replace_record)
                            else:  # Again, no tunnel_id provided means delete intent
                                delete_record = record_batch_params.Delete(id=record.id)
                                zone_records.deletes.append(delete_record)
                        else:
                            raise RuntimeError(
                                f"Subdomain {record.name} is held by some other tunnel, {tid} `-force` to override")
                    elif not isinstance(domain_subdomain_mapping,
                                        All):  # subdomain is held by non-tunnel service, if ALL, we not need to throw any error for it, as the user didn't ask for it explicitly
                        raise RuntimeError(
                            f"Subdomain {record.name} is held by some other service, NOT tunnel, cannot modify!")

            if tunnel_id:
                new_records = [
                    CNAMERecordParam(
                        name=subdomain,
                        type="CNAME",
                        content=content,
                        # comment=comment,
                        proxied=True,
                    )
                    for subdomain in zone_domains or []
                ]
                zone_records.creates.extend(new_records)
            # No else clause, because you cannot delete what doesn't exist!

            if zone_records:
                zone_response = await self.tunnel_service.dns_edit(zone_records)
                responses.append((zone, zone_response))

        async def each_zone(zone: ZoneEntry):
            await scan_tunnels(zone.account_id)
            await set_zone_dns(zone)

        async def body():  # to prevent hint clash
            async with asyncio.TaskGroup() as tg:
                # zones = await smart_cache.zone_memory
                for zone in zones:
                    _ = tg.create_task(each_zone(zone))

        await body()
        return responses

    async def cleanup(self, everything: bool = False, ):
        zones = await self.tunnel_service.get_zones()
        _ = await self._configure_dns(
            zones=zones,
            domain_subdomain_mapping=ALL,
            tunnel_id=None,
            epimeral=False,
            force=everything,
        )

    async def _tunnel_detail(self, zone: ZoneEntry, name: str):
        aid = zone.account_id
        tunnel: CloudflareTunnel | None = None
        async for i in self.tunnel_service.tunnel_list(aid, name):
            tunnel = i
        if not tunnel:
            return None

        tunnel_token = await self.tunnel_service.tunnel_token(tunnel)
        return TokenizedTunnel(
            id=tunnel.id,  # pyright: ignore[reportArgumentType]
            account_id=aid,
            name=tunnel.name,  # pyright: ignore[reportArgumentType]
            created_at=tunnel.created_at,  # pyright: ignore[reportArgumentType]
            tunnel_token=SecretStr(tunnel_token),
        )

    async def _get_or_create_tunnel(self, zone: ZoneEntry, name: str | None):
        tunnel = (name and await self._tunnel_detail(zone, name)) or await self.tunnel_service.create_tunnel(zone, name)
        return tunnel

    async def subdomain_mapped_tunnel(
            self,
            mappings: Sequence[Mapping],
            tunnel_name: str | None = None,
            force: bool = False,
    ):
        if not mappings:
            raise RuntimeError("No mappings provided")

        domain_subdomain_mapping: DomainSubDomainMapping = defaultdict(set)  # Domain ->subdomains
        for mapping in mappings:
            subdomain = mapping.subdomain.str_rep
            domain = domain_from_subdomain(subdomain)
            domain_subdomain_mapping[domain].add(subdomain)

        zones = await self.tunnel_service.get_zones(domain_subdomain_mapping.keys())
        primary_zone = zones[0]
        is_ephemeral = tunnel_name is None

        ingresses = (
            service.ingress(subdomain)
            for subdomain, service in mappings
        )
        # Find the update list
        ingresses = fix_ingress_order(ingresses)

        tunnel = await self._get_or_create_tunnel(primary_zone, tunnel_name)
        async with asyncio.TaskGroup() as tg:
            # Update tunnel with ingresses and create DNS records in async
            response_task = tg.create_task(self._configure_dns(
                zones=zones,
                domain_subdomain_mapping=domain_subdomain_mapping,
                tunnel_id=tunnel.id,
                epimeral=is_ephemeral,
                force=force,
            ))
            _ = tg.create_task(self.tunnel_service.update_tunnel_ingress(tunnel, ingresses))

        responses = response_task.result()

        async def clean_up():
            logger.info(f"Cleaning up tunnel: {tunnel.name}")
            await self.tunnel_service.force_delete_tunnel(tunnel)
            async with asyncio.TaskGroup() as tg:
                for response in responses:
                    _ = tg.create_task(self.tunnel_service.dns_edit(delify_response(*response)))
            logger.info(f"Cleaned up tunnel: {tunnel.name}")

        return ConfiguredTunnel(tunnel, responses, clean_up)
