import asyncio
import socket
from collections import defaultdict
from datetime import datetime, timezone

from cloudflare import AsyncCloudflare
from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import record_batch_params
from cloudflare.types.dns.record_response import CNAMERecord
from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import ConfigIngress, Config
from cloudflare.types.zones import Zone
from pydantic import SecretStr

from pyflared import consts
from pyflared.api.createtunnel import CreatedTunnel, create_tunnel
from pyflared.types import ZoneNameDict, Domain, ZoneId, ZoneNames, Mappings, TunnelIds, CreationRecords


def auto_tunnel_name() -> str:
    device_name = socket.gethostname()
    now = datetime.now()
    return device_name + "_" + now.strftime("%Y%m%d_%H%M%S")


def _tunnel_id(record: CNAMERecord) -> str | None:
    return record.content.removesuffix(consts.cfargotunnel) if record.content else None


def _is_orphan(tunnel: CloudflareTunnel) -> bool:
    # has tag, inactive + time, down
    # now = datetime.now(timezone.utc)
    # threshold = now - timedelta(seconds=5)
    # return tunnel.metadata.get(_tag) and (
    #         (tunnel.status == "inactive" and tunnel.created_at < threshold) or (
    #         tunnel.status == "down" and tunnel.conns_inactive_at and tunnel.conns_inactive_at < threshold)
    # )
    return tunnel.metadata.get(consts.tag) and tunnel.status in ("inactive", "down")


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
    async def del_tunnel(self, tunnel: CloudflareTunnel):
        async with self.semaphore:
            await self.client.zero_trust.tunnels.cloudflared.delete(
                tunnel_id=tunnel.id, account_id=tunnel.account_tag)  # type: ignore

    async def batch_dns_create(self, zone_id: ZoneId, records: list[record_batch_params.CNAMERecordParam]):
        async with self.semaphore:
            await self.client.dns.records.batch(zone_id=zone_id, posts=records)

    async def update_tunnel(self, tunnel_id: str, account_id: str, ingresses: list[ConfigIngress]):
        async with self.semaphore:
            await self.client.zero_trust.tunnels.cloudflared.configurations.update(
                tunnel_id=tunnel_id, account_id=account_id, config=Config(ingress=ingresses)
            )

    # Easy methods
    async def remove_orphans_tunnels_from_account(self, account_id: str, available: TunnelIds):  # tunnel_id
        tunnels = self.tunnels(account_id=account_id)
        async with asyncio.TaskGroup() as tg:
            async for tunnel in tunnels:
                if _is_orphan(tunnel):
                    tg.create_task(self.del_tunnel(tunnel))
                else:
                    available.add(tunnel.id)

    async def remove_orphans_dns_from_zone(self, zone_id: str, available_tunnels: set[str], check_time: datetime):
        deletes: defaultdict[str, list[record_batch_params.Delete]] = defaultdict()  # zone_id -> deleteList

        async for record in self.cname_records(zone_id=zone_id):
            if record.created_on < check_time and _tunnel_id(record) not in available_tunnels:
                deletes[zone_id].append(record_batch_params.Delete(id=record.id))

        async with asyncio.TaskGroup() as tg:
            for zone_id, delete_list in deletes.items():
                tg.create_task(self.client.dns.records.batch(zone_id=zone_id, deletes=delete_list))

    async def remove_orphans(self):
        check_time = datetime.now(timezone.utc)

        async with asyncio.TaskGroup() as tg:
            available_tunnels = TunnelIds()
            async for account in self.accounts():
                tg.create_task(self.remove_orphans_tunnels_from_account(account.id, available_tunnels))

        # Delete orphan DNS records
        async with asyncio.TaskGroup() as tg:
            async for zone in self.zones():
                tg.create_task(self.remove_orphans_dns_from_zone(zone.id, available_tunnels, check_time))

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

    async def make_tunnel(self, account_id: str) -> CloudflareTunnel:
        tunnel = self.client.zero_trust.tunnels.cloudflared.create(
            account_id=account_id,
            name=auto_tunnel_name(),
            extra_body={
                "metadata": {
                    consts.tag: False
                }
            }
        )
        return await tunnel  # type: ignore

    async def create_auto_tunnel(self, account_id: str) -> CreatedTunnel:
        return await create_tunnel(
            api_token=self.client.api_token,  # type: ignore
            account_id=account_id,
            tunnel_name=auto_tunnel_name(),
            metadata={consts.tag: False}
        )

    async def fixed_dns_tunnel(self, mappings: Mappings) -> SecretStr:  # Tunnel Token
        if not mappings:
            raise Exception("No mappings provided")

        # Check if dns is already mapped by someone else
        all_records = await self.all_dns_records()
        common_names = all_records & mappings.keys()
        if common_names:
            raise Exception(f"Domain(s) already mapped: {common_names}")

        # make tunnel
        zone_dict = await self.zone_name_dict()

        first_domain, _ = dict_first(mappings)
        first_zone = find_zone(zone_dict, first_domain)

        tunnel = await self.create_auto_tunnel(first_zone.account.id)  # type: ignore

        ingresses = [
            ConfigIngress(service="http_status:404")  # type: ignore # default fallback
        ]
        creation_records = CreationRecords()

        for (domain, service) in mappings.items():
            ingresses.append(
                ConfigIngress(hostname=domain, service=service)
            )

            zone = find_zone(zone_dict, domain)
            record = tunnel.dns_record(domain)
            creation_records[zone.id].append(record)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.update_created(tunnel, ingresses))
            tg.create_task(self.easy_batch_dns_create(creation_records))

        return tunnel.secret

    async def update_created(self, tunnel: CreatedTunnel, ingresses: list[ConfigIngress]):
        await self.update_tunnel(tunnel_id=tunnel.id, account_id=tunnel.account_id, ingresses=ingresses)

    async def easy_batch_dns_create(self, creation_records: CreationRecords):
        async with asyncio.TaskGroup() as tg:
            for zone_id, new_records in creation_records.items():
                tg.create_task(self.batch_dns_create(zone_id, new_records))
