import asyncio
import re
import socket
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Final, Literal

from beartype import beartype
from cloudflare import AsyncCloudflare, BadRequestError
from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import record_batch_params
from cloudflare.types.dns.record_response import CNAMERecord
from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import Config, ConfigIngress
from cloudflare.types.zones import Zone
from loguru import logger
from pydantic import SecretStr

from pyflared import consts
from pyflared.api_sdk.fetch import fetch_zones_account_ids
from pyflared.api_sdk.types import CustomTunnel
from pyflared.log.pretty import Pretty
from pyflared.shared.types import CreationRecords, Domain, Mappings, TunnelIds, ZoneId, ZoneNameDict, ZoneNames

active_connection_error_code: Final[int] = 1022


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


def _tunnel_id(record: CNAMERecord) -> str | None:
    return record.content.removesuffix(consts.cfargotunnel) if record.content.endswith(consts.cfargotunnel) else None


def _is_orphan(tunnel: CloudflareTunnel) -> bool:
    # has tag, inactive + time, down
    # now = datetime.now(timezone.utc)
    # threshold = now - timedelta(seconds=5)
    # return tunnel.metadata.get(_tag) and (
    #         (tunnel.status == "inactive" and tunnel.created_at < threshold) or (
    #         tunnel.status == "down" and tunnel.conns_inactive_at and tunnel.conns_inactive_at < threshold)
    # )
    # Must have our tag + inactive or down (0 or -1 connections)
    return tunnel.metadata.get(consts.api_managed_tag) and tunnel.status in ("inactive", "down")


def find_zone(zones: ZoneNameDict, domain: Domain) -> Zone:
    domain_clean = domain.lower()
    parts = domain_clean.split('.')

    # 2. Find Zone
    for i in range(len(parts)):
        candidate = ".".join(parts[i:])
        if found_zone := zones.get(candidate):
            return found_zone
    raise ValueError(f"No matching zone found for: {domain}")


def dict_first[K, V](d: dict[K, V]) -> tuple[K, V]:
    return next(iter(d.items()))


class TunnelManager:
    def __init__(self, api_token: str | None = None):
        self.client = AsyncCloudflare(api_token=api_token)
        self.semaphore = asyncio.Semaphore(16)

    def accounts(self):
        return self.client.accounts.list()

    def zones(self):
        return self.client.zones.list()

    def tunnels(self, account_id: str):
        return self.client.zero_trust.tunnels.cloudflared.list(account_id=account_id, is_deleted=False)

    def cname_records(self, zone_id: str):
        return self.client.dns.records.list(zone_id=zone_id, type="CNAME")

    # Almost direct methods
    async def delete_tunnel(self, tunnel: CloudflareTunnel):
        logger.info(f"Deleting orphan tunnel: {tunnel.name}")
        async with self.semaphore:
            result = await self.client.zero_trust.tunnels.cloudflared.delete(
                tunnel_id=tunnel.id, account_id=tunnel.account_tag)  # type: ignore
            logger.debug(f"Deletion result: {Pretty(result.model_dump())}")

    async def cleanup_tunnel_connection(self, tunnel: CloudflareTunnel):
        # 2. Delete the active connections (The "Cleanup" step)
        # This is the API equivalent of `cloudflared tunnel cleanup`
        logger.info(f"Cleaning up ghost connections: {tunnel.name}")
        async with self.semaphore:
            result = await self.client.zero_trust.tunnels.cloudflared.connections.delete(
                tunnel_id=tunnel.id, account_id=tunnel.account_tag)
            logger.debug("Cleanup result: {}", Pretty(result))

    async def force_delete_tunnel(self, tunnel: CloudflareTunnel):
        try:
            await self.delete_tunnel(tunnel)
        except BadRequestError as e:
            error_codes = (err.code for err in e.errors)

            if active_connection_error_code in error_codes:
                await self.cleanup_tunnel_connection(tunnel)
                # retry
                await self.delete_tunnel(tunnel)
            else:
                # Re-raise if it's a different error (e.g., auth, permissions)
                raise

    async def batch_dns_create(self, zone_id: ZoneId, records: list[record_batch_params.CNAMERecordParam]):
        async with self.semaphore:
            logger.info(f"Creating DNS records: {Pretty([record['name'] for record in records])}")
            logger.debug(f"DNS records: {Pretty(records)}")
            result = await self.client.dns.records.batch(zone_id=zone_id, posts=records, )
            logger.debug(f"Batch creation result: {Pretty(result.model_dump())}")

    async def zone_batch_delete_dns(self, zone_id: ZoneId, deletes: Iterable[record_batch_params.Delete]):
        if not deletes:
            return
        logger.info(f"Orphan DNS records found: {Pretty(deletes)}")
        async with self.semaphore:
            result = await self.client.dns.records.batch(zone_id=zone_id, deletes=deletes)
        logger.debug(f"Batch deletion result: {Pretty(result.model_dump())}")

    async def update_tunnel(self, tunnel_id: str, account_id: str, ingresses: list[ConfigIngress]):
        async with self.semaphore:
            await self.client.zero_trust.tunnels.cloudflared.configurations.update(
                tunnel_id=tunnel_id, account_id=account_id, config=Config(ingress=ingresses)
            )

    # Easy methods
    async def remove_orphans_tunnels_from_account(self, account_id: str, available: TunnelIds):  # tunnel_id
        logger.info(f"Checking for orphan tunnels in account: {account_id}")
        tunnels = self.tunnels(account_id=account_id)
        async with asyncio.TaskGroup() as tg:
            async for tunnel in tunnels:
                if _is_orphan(tunnel):
                    tg.create_task(self.force_delete_tunnel(tunnel))
                else:
                    available.add(tunnel.id)

    async def remove_orphans_dns_from_zone(self, zone_id: str, active_tunnels: set[str], check_time: datetime):
        deletes = [
            record_batch_params.Delete(id=record.id)
            async for record in self.cname_records(zone_id=zone_id)
            if consts.api_managed_tag in (record.comment or "")
               and record.created_on < check_time
               and _tunnel_id(record) not in active_tunnels
        ]
        if deletes:
            await self.zone_batch_delete_dns(zone_id=zone_id, deletes=deletes)

    async def remove_orphans(self):
        logger.info("Checking for orphan tunnels and DNS records...")
        tunnel_check_time = datetime.now(UTC)

        # We are requesting the zones first and collecting the account_ids to bypass 1 less network call
        zone_ids, account_ids = await fetch_zones_account_ids(self.client)

        # Iterate over all tunnels and collect active ones
        active_tunnels = TunnelIds()
        async with asyncio.TaskGroup() as tg:
            # async for account in self.accounts():
            for account_id in account_ids:
                logger.info(f"Checking account: {account_id}")
                tg.create_task(self.remove_orphans_tunnels_from_account(account_id, active_tunnels))

        # Delete orphan DNS records
        async with asyncio.TaskGroup() as tg:
            for zone in zone_ids:
                tg.create_task(self.remove_orphans_dns_from_zone(zone, active_tunnels, tunnel_check_time))

    async def all_dns_records(self) -> ZoneNames:
        record_set = ZoneNames()

        async def record_from_zone(zone_id: str):
            async for record in self.cname_records(zone_id=zone_id):
                record_set.add(record.name)

        async with asyncio.TaskGroup() as tg:
            async for zone in self.zones():
                tg.create_task(record_from_zone(zone.id))

        return record_set

    # async def mapped_zone(self, domain: str) -> Zone:
    #     async for zone in self.zones():  # have a dedicated api method to get zone by domain
    #         if domain.endswith(zone.name):
    #             return zone
    #     raise Exception(f"No matching zone found for: {domain}")

    async def zone_name_dict(self) -> ZoneNameDict:
        zones = ZoneNameDict()
        async for zone in self.zones():
            zones[zone.name] = zone
        return zones

    @beartype
    async def create_tunnel(
            self,  # Pass the SDK client directly
            account_id: str,
            tunnel_name: str,
            config_src: Literal["cloudflare", "local"] = "cloudflare",
            metadata: dict[str, Any] | None = None
    ) -> CustomTunnel:
        create_tunnel_endpoint = f"accounts/{account_id}/cfd_tunnel"  # SDK handles base URL

        payload: dict[str, Any] = {
            "name": tunnel_name,
            "config_src": config_src
        }
        if metadata:
            payload["metadata"] = metadata

        # Use the SDK's internal helper to make raw requests
        # This automatically handles Auth, Base URL, and Retries
        response = await self.client.post(
            create_tunnel_endpoint,
            body=payload,
            cast_to=dict  # Tell SDK to return a raw dict
        )

        return CustomTunnel.from_cloudflare_response(response)

    async def create_auto_tunnel(self, account_id: str, tunnel_name: str | None = None) -> CustomTunnel:
        if not tunnel_name:
            tunnel_name = auto_tunnel_name()
        # logger.info(f"Creating tunnel {tunnel_name}...")
        async with self.semaphore:
            return await self.create_tunnel(
                account_id=account_id,
                tunnel_name=tunnel_name,
                metadata={consts.api_managed_tag: True},
                api_token=self.client.api_token,  # type: ignore #This also helpful because their client also checks env
            )

    async def fixed_dns_tunnel(
            self, mappings: Mappings,
            tunnel_name: str | None = None) -> SecretStr:  # Tunnel Token

        if not mappings:
            raise RuntimeError("No mappings provided")

        # Check if dns is already mapped by someone else
        all_records = await self.all_dns_records()
        common_names = all_records & mappings.keys()
        if common_names:
            raise RuntimeError(f"Domain(s) already mapped: {Pretty(common_names)}")

        # Find the zone for the first domain
        zone_dict = await self.zone_name_dict()

        first_domain, _ = dict_first(mappings)
        first_zone = find_zone(zone_dict, first_domain)

        # Make tunnel on first matched zone #TODO: Check if tunnel can be created with the ingresses in one go
        tunnel = await self.create_auto_tunnel(first_zone.account.id, tunnel_name=tunnel_name)

        # Create DNS records
        ingresses: list[ConfigIngress] = []
        creation_records = CreationRecords()

        for (domain, service) in mappings.items():
            ingresses.append(
                ConfigIngress(hostname=domain, service=service)
            )

            zone = find_zone(zone_dict, domain)
            record = tunnel.build_dns_record(domain)
            creation_records[zone.id].append(record)

        ingresses.append(
            # ConfigIngress(hostname="*." + first_zone.name, service="http://127.0.0.1:8080"),
            ConfigIngress(service="http_status:404"),  # type: ignore # default fallback
        )

        async with asyncio.TaskGroup() as tg:
            # Update tunnel with ingresses and create DNS records in async

            tg.create_task(self.update_created(tunnel, ingresses))
            tg.create_task(self.easy_batch_dns_create(creation_records))

        return tunnel.token

    async def update_created(self, tunnel: CustomTunnel, ingresses: list[ConfigIngress]):
        await self.update_tunnel(tunnel_id=str(tunnel.id), account_id=tunnel.account_id, ingresses=ingresses)

    async def easy_batch_dns_create(self, creation_records: CreationRecords):
        async with asyncio.TaskGroup() as tg:
            for zone_id, new_records in creation_records.items():
                tg.create_task(self.batch_dns_create(zone_id, new_records))
