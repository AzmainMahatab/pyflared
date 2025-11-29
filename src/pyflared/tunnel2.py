import asyncio
import socket
from collections import defaultdict
from datetime import datetime, timezone

from cloudflare import AsyncCloudflare
from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import record_batch_params
from cloudflare.types.dns.record_response import CNAMERecord
from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import ConfigIngress
from cloudflare.types.zones import Zone

from pyflared.tunnel import Mapping

_tag = "pyflared-managed"

_cfargotunnel = ".cfargotunnel.com"


def _is_orphan(tunnel: CloudflareTunnel) -> bool:
    # has tag, inactive + time, down
    # now = datetime.now(timezone.utc)
    # threshold = now - timedelta(seconds=5)
    # return tunnel.metadata.get(_tag) and (
    #         (tunnel.status == "inactive" and tunnel.created_at < threshold) or (
    #         tunnel.status == "down" and tunnel.conns_inactive_at and tunnel.conns_inactive_at < threshold)
    # )
    return tunnel.metadata.get(_tag) and tunnel.status in ("inactive", "down")  # type: ignore


def _tunnel_id(record: CNAMERecord) -> str | None:
    return record.content.removesuffix(_cfargotunnel) if record.content else None


class TunnelManager:
    def __init__(self, api_token: str):
        self.client = AsyncCloudflare(api_token=api_token)
        self.semaphore = asyncio.Semaphore(16)

    def accounts(self):
        return self.client.accounts.list()

    def zones(self):
        return self.client.zones.list()

    def tunnels(self, account_id: str):
        return self.client.zero_trust.tunnels.cloudflared.list(account_id=account_id, is_deleted=False)

    def dns_records(self, zone_id: str):
        return self.client.dns.records.list(zone_id=zone_id, type="CNAME")

    # async def freeze_dns_records(self, zone_id: str) -> list[CNAMERecord]:
    #     x = await self.client.dns.records.list(zone_id=zone_id, type="CNAME")
    #     return x.result
    #
    # async def freeze

    async def del_tunnel(self, tunnel: CloudflareTunnel):
        async with self.semaphore:
            await self.client.zero_trust.tunnels.cloudflared.delete(
                tunnel_id=tunnel.id, account_id=tunnel.account_tag)  # type: ignore

    async def remove_orphans_tunnels_from_account(self, account_id: str, available: set[str]):
        tunnels = self.tunnels(account_id=account_id)
        async with asyncio.TaskGroup() as tg:
            async for tunnel in tunnels:
                if _is_orphan(tunnel):
                    tg.create_task(self.del_tunnel(tunnel))
                else:
                    available.add(tunnel.id)

    async def remove_orphans_tunnels_from_zone(self, zone: Zone, deleted):
        tunnels = self.tunnels(account_id=zone.account.id)

    async def remove_orphans_dns_from_zone(self, zone_id: str, available_tunnels: set[str], check_time: datetime):
        deletes: defaultdict[str, list[record_batch_params.Delete]] = defaultdict()  # zone_id -> deleteList

        async for record in self.dns_records(zone_id=zone_id):
            if record.created_on < check_time and _tunnel_id(record) not in available_tunnels:
                deletes[zone_id].append(record_batch_params.Delete(id=record.id))

        async with asyncio.TaskGroup() as tg:
            for zone_id, delete_list in deletes.items():
                tg.create_task(self.client.dns.records.batch(zone_id=zone_id, deletes=delete_list))

    async def remove_orphans(self):
        available_tunnels: set[str] = set()

        check_time = datetime.now(timezone.utc)
        # Delete orphan tunnels
        async with asyncio.TaskGroup() as tg:
            async for account in self.accounts():
                tg.create_task(self.remove_orphans_tunnels_from_account(account.id, available_tunnels))

        # Delete orphan DNS records
        async with asyncio.TaskGroup() as tg:
            async for zone in self.zones():
                tg.create_task(self.remove_orphans_dns_from_zone(zone.id, available_tunnels, check_time))

    async def all_dns_records(self) -> set[str]:
        record_set = set[str]()

        async def record_from_zone(zone_id: str):
            async for record in self.dns_records(zone_id=zone_id):
                record_set.add(record.name)

        async with asyncio.TaskGroup() as tg:
            async for zone in self.zones():
                tg.create_task(record_from_zone(zone.id))

        return record_set

    async def mapped_zone(self, domain: str) -> Zone:
        async for zone in self.zones():  # have a dedicated api method to get zone by domain
            if domain.endswith(zone.name):
                return zone
        raise Exception(f"No matching zone found for: {domain}")

    async def tunnel(self, *mappings: Mapping) -> str:  # Tunnel Token
        if not mappings:
            raise Exception("No mappings provided")

        zt = asyncio.create_task(self.mapped_zone(mappings[0].domain))

        all_records = await self.all_dns_records()

        domains = {x.domain for x in mappings}
        common_names = all_records & domains

        if common_names:
            raise Exception(f"Domain(s) already mapped: {common_names}")

        # make tunnel
        device_name = socket.gethostname()
        now = datetime.now()

        z = await zt
        tunnel = self.client.zero_trust.tunnels.cloudflared.create(
            account_id=z.account.id,  # type: ignore
            name=device_name + "_" + now.strftime("%Y%m%d_%H%M%S"),
            extra_body={
                "metadata": {
                    _tag: False
                }
            }
        )

        zone_set = {z.name: z for z in self.zones()}

        ingresses = [
            ConfigIngress(service="http_status:404")  # default fallback
        ]
        for mapping in mappings:
            self.zones_for_domains2x(
                zoned_records, zone_set, mapping,
                tunnel.id  # type: ignore
            )
            ingresses.append(
                ConfigIngress(
                    hostname=mapping.domain,
                    service=mapping.service.unicode_string(),
                )
            )

    def zones_for_domains2x(
            self,
            grouped: defaultdict[str, list[record_batch_params.CNAMERecordParam]],
            zone_set: dict[str, Zone],
            mapping: Mapping,
            tunnel_id: str, ):

        domain = mapping.domain
        domain_clean = domain.lower()
        parts = domain_clean.split('.')
        found_zone: Zone | None = None

        # 2. Find Zone
        for i in range(len(parts)):
            candidate = ".".join(parts[i:])
            if found_zone := zone_set.get(candidate):
                record = record_batch_params.CNAMERecordParam(
                    name=domain,
                    type="CNAME",
                    content=_dns_content(tunnel_id),
                    proxied=True,
                    comment=_tag,
                )
                grouped[found_zone.id].append(record)
                break

        if not found_zone:
            raise ValueError(f"No matching zone found for: {domain}")
        return grouped
