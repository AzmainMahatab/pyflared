import socket
from collections import defaultdict
from datetime import datetime
from functools import cache
from typing import Iterator, Generator, Any

from cloudflare import Cloudflare
from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import record_list_params, record_batch_params
from cloudflare.types.dns.record_response import CNAMERecord
from cloudflare.types.zero_trust.tunnel_list_response import TunnelWARPConnectorTunnel
from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import Config, ConfigIngress
from cloudflare.types.zones import Zone
from pydantic import HttpUrl
from pydantic.dataclasses import dataclass

from pyflared import cloudflared
from pyflared.A import ZoneRecords


@dataclass
class Mapping:
    domain: str
    service: HttpUrl


_tag = "pyflared-managed"

_cfargotunnel = ".cfargotunnel.com"


def _tunnel_id(record: CNAMERecord) -> str:
    return record.content.removesuffix(_cfargotunnel)


def _dns_content(tunnel_id: str) -> str:
    return f"{tunnel_id}{_cfargotunnel}"


def _is_orphan(tunnel: CloudflareTunnel) -> bool:
    # has tag, inactive + time, down
    # now = datetime.now(timezone.utc)
    # threshold = now - timedelta(seconds=5)
    # return tunnel.metadata.get(_tag) and (
    #         (tunnel.status == "inactive" and tunnel.created_at < threshold) or (
    #         tunnel.status == "down" and tunnel.conns_inactive_at and tunnel.conns_inactive_at < threshold)
    # )
    return tunnel.metadata.get(_tag) and tunnel.status in ("inactive", "down")


class TunnelManager:
    def __init__(self, api_token: str):
        self.client = Cloudflare(api_token=api_token)
        default_account = self.client.accounts.list().result[0]

    @cache
    def initial_accounts(self):
        return self.client.accounts.list().result

    @cache
    def initial_zones(self):
        return self.client.zones.list().result

    def remove_orphans(self):
        # get all dns
        zone_records = self.all_cname_records()

        # get all tunnels
        tunnels: dict[str, CloudflareTunnel] = {}  # tunnel.id -> tunnel
        for account in self.initial_accounts():
            a_tunnels: list[CloudflareTunnel] = self.client.zero_trust.tunnels.cloudflared.list(
                account_id=account.id).result # type: ignore

            for tunnel in a_tunnels:
                if _is_orphan(tunnel):
                    self._remove_tunnel(tunnel)
                else:
                    tunnels[tunnel.id] = tunnel

        # remove all dns from the list which doesn't exist in tunnel list
        rem_candidates: defaultdict[str, list[record_batch_params.Delete]] = defaultdict(list)  # zone_id -> deletes
        for zone_id, record_list in zone_records.items():
            for record in record_list:
                if _tunnel_id(record) not in tunnels.keys():
                    del_id = record_batch_params.Delete(id=record.id)
                    rem_candidates[zone_id].append(del_id)

        for zone_id, deletes in rem_candidates.items():
            self.client.dns.records.batch(
                zone_id=zone_id, deletes=deletes)

    def tunnel2(self, *mappings: Mapping):
        if not mappings:
            return

        # Cleanup is done, check if the domain is still blocked by someone
        mapped_domains = {x.name for sublist in self.all_cname_records().values() for x in sublist}
        domains = {x.domain for x in mappings}

        common_names = mapped_domains & domains
        if common_names:
            raise Exception(f"Domain(s) already mapped: {common_names}")

        # make tunnel
        device_name = socket.gethostname()
        now = datetime.now()

        tunnel = self.client.zero_trust.tunnels.cloudflared.create(
            account_id=self.initial_accounts()[0].id,
            name=device_name + "_" + now.strftime("%Y%m%d_%H%M%S"),
            extra_body={
                "metadata": {
                    _tag: False
                }
            }
        )

        zoned_records: defaultdict[str, list[record_batch_params.CNAMERecordParam]] = defaultdict(
            list)  # zone_id -> records
        zone_set = {z.name: z for z in self.initial_zones()}

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

        self.client.zero_trust.tunnels.cloudflared.configurations.update(
            account_id=tunnel.account_tag,  # type: ignore
            tunnel_id=tunnel.id,  # type: ignore
            config=Config(ingress=ingresses)
        )

        for zone_id, new_records in zoned_records.items():
            self.client.dns.records.batch(posts=new_records, zone_id=zone_id)

        token = self.client.zero_trust.tunnels.cloudflared.token.get(tunnel_id=tunnel.id, account_id=tunnel.account_tag)

        return token

    def f1(self, *mappings: Mapping):
        self.remove_orphans()
        tunnel_token = self.tunnel2(*mappings)
        binary.cloudflared(["tunnel", "run", "--token", tunnel_token])

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

    def all_cname_records(self) -> ZoneRecords:
        records: ZoneRecords = {}
        for zone in self.initial_zones():
            records[zone.id] = self.client.dns.records.list(zone_id=zone.id, type="CNAME").result
        return records

    def _accessible_zones(self) -> list[Zone]:
        return self.client.zones.list().result

    def retry(self):
        zones = self._accessible_zones()

        for zone in zones:
            tunnels = self._zone_tunnels(zone)

            for tunnel in tunnels:
                if _is_orphan(tunnel):
                    self._remove_tunnel(tunnel)

        pass

    def retry2(self, *mappings: Mapping):
        accounts = self.client.accounts.list().result

        for account in accounts:
            tunnels = self.client.zero_trust.tunnels.cloudflared.list(
                account_id=account.id, is_deleted=False).result

            for tunnel in tunnels:
                if False:
                    pass
                elif _is_orphan(tunnel):
                    self._remove_tunnel(tunnel)

    pass

    def _zone_for_domain(self, domain: str) -> Zone:
        return next(i for i in self._accessible_zones() if domain.endswith(i.name))

    def _zone_tunnels(self, zone: Zone) -> list[CloudflareTunnel]:
        return self.client.zero_trust.tunnels.cloudflared.list(
            account_id=zone.account.id)

    def _remove_tunnel(self, tunnel: CloudflareTunnel):
        self.client.zero_trust.tunnels.cloudflared.delete(
            tunnel_id=tunnel.id, account_id=tunnel.account_tag)

    def _delete_tunnel_w_associated_dns(self, tunnel: CloudflareTunnel):
        self.client.zero_trust.tunnels.cloudflared.delete(
            tunnel_id=tunnel.id, account_id=tunnel.account_tag)

    def _orphan_tunnels2(self) -> Iterator[CloudflareTunnel]:
        for zone in self._accessible_zones():
            yield from self._orphan_tunnels(zone)

        # orphans = self.client.zero_trust.tunnels.cloudflared.list(
        #     account_id=zone.account.id, is_deleted=False).result
        # return filter(_is_orphan, orphans)

    def _orphan_tunnels(self, zone: Zone) -> Iterator[CloudflareTunnel]:
        orphans = self.client.zero_trust.tunnels.cloudflared.list(
            account_id=zone.account.id, is_deleted=False).result
        return filter(_is_orphan, orphans)

    def _orphan_tunnels3(self) -> Iterator[CloudflareTunnel]:
        for zone in self._accessible_zones():
            orphans = self.client.zero_trust.tunnels.cloudflared.list(
                account_id=zone.account.id, is_deleted=False).result

    def _remove_orphan_tunnels(self, zone: Zone):
        orphan_tunnels = []
        for i in self._orphan_tunnels(zone):
            self._delete_tunnel_w_associated_dns(i)
            orphan_tunnels.append(i)
        return orphan_tunnels

    def _remove_orphans(self):
        pass

    def find_orphan_dns_records(self):
        pass

    def delete_orphan_dns_records(self):
        self.find_orphan_dns_records()
        pass

    def _create_dns_record(
            self, zone_id: str, record_id: str | None, domain: str, tunnel_id: str):

        if record_id:
            self.client.dns.records.update(
                dns_record_id=record_id,
                zone_id=zone_id,
                name=domain,
                type="CNAME",
                content=_dns_content(tunnel_id),
                proxied=True,
                comment=_tag,
            )
        else:
            self.client.dns.records.create(
                zone_id=zone_id,
                name=domain,
                type="CNAME",
                content=_dns_content(tunnel_id),
                proxied=True,
                comment=_tag,
            )

    def _linked_zone(self, tunnel_id: str):
        self.client.dns.records.list(
            zone_id=my_zone.id,
            content=record_list_params.Content(startswith=tid))

        pass

    def _linked_dns_records(self, tunnel_id: str):

        zone = self._zone_for_domain(domain)
        record_list = self.client.dns.records.list(
            zone_id=zone.id,
            name=record_list_params.Name(exact=domain))

    def del_orphans(self):
        orpahns: set[] = set()
        self._orphan_tunnels()

        pass

    def del_orphans23(self):
        for zone in self._accessible_zones():
            # : list[CNAMERecord]
            records = self.client.dns.records.list(
                zone_id=zone.id, type="CNAME").result
            for record in records:
                record.

        pass

    def fx1(self):
        zones = self._accessible_zones()
        # dns_records: list[CNAMERecord] = []
        dns_records: dict[str, CNAMERecord] = {}
        orphan_tunnels: dict[str, CloudflareTunnel] = {}
        # tunnels: list[CloudflareTunnel] = []

        for zone in zones:
            z_records: list[CNAMERecord] = self.client.dns.records.list(
                zone_id=zone.id, type="CNAME").result
            for record in z_records:
                dns_records[record.name] = record

            z_tunnels = self.client.zero_trust.tunnels.cloudflared.list(
                account_id=zone.account.id)
            for z_tunnel in filter(_is_orphan, z_tunnels):
                orphan_tunnels[z_tunnel.id] = z_tunnel

        orphan_records = [x for x in dns_records.values() if _tunnel_id(x) in orphan_tunnels]

        for orphan_record in orphan_records:
            self.client.dns.records.delete(
                dns_record_id=orphan_record.id)
        for orphan_tunnel in orphan_tunnels.values():
            self.client.zero_trust.tunnels.cloudflared.delete(
                tunnel_id=orphan_tunnel.id)

        pass

    def fx2(self):
        zones = self._accessible_zones()

        for zone in zones:
            records: list[CNAMERecord] = self.client.dns.records.list(
                zone_id=zone.id, type="CNAME").result

            record_dict: defaultdict[str, list] = defaultdict(list)
            for record in records:
                record_dict[_tunnel_id(record)].append(record)

            tunnels: list[CloudflareTunnel] = self.client.zero_trust.tunnels.cloudflared.list(
                account_id=zone.account.id).result  # pass extra metadata for tag?
            for tunnel in tunnels:
                if _is_orphan(tunnel):
                    self.client.zero_trust.tunnels.cloudflared.delete(
                        tunnel_id=tunnel.id, account_id=zone.account.id)
                    linked_records = record_dict[tunnel.id]
                    for record in linked_records:
                        self.client.dns.records.delete(
                            dns_record_id=record.id, zone_id=zone.id)

    def del_orphans2(self):
        # Scan all tunnels - From all zones
        # Scan all records - From all zones (
        # Use Filtering to find orphans
        zones = self._accessible_zones()
        accounts = self.client.accounts.list()

        for account in accounts:
            t = self.client.zero_trust.tunnels.cloudflared.list(
                account_id=account.id, is_deleted=False).result

        orphans_tunnels = set[CloudflareTunnel]()

        for zone in zones:
            tunnels = self.client.zero_trust.tunnels.cloudflared.list(
                account_id=zone.account.id, is_deleted=False).result
            for tunnel in tunnels:
                if _is_orphan(tunnel):
                    orphans_tunnels.add(tunnel)
                    self._remove_tunnel(tunnel)

        # Find associated DNS records
        for zone in zones:
            dns_records = self.client.dns.records.list(
                zone_id=zone.id)
            for record in dns_records:
                if record.content in orphans_tunnels:
                    self.client.dns.records.delete(
                        dns_record_id=record.id, zone_id=zone.id)

        pass

    def mappings_to_zones2(self, *domains: str) -> Generator[tuple[str, Zone], Any, None]:
        zones = self._accessible_zones()
        return (domain, next(zone for zone in zones if domain.endswith(zone.name)) for domain in domains)

    def _find_zone(self, zones: list[Zone], domain: str) -> Zone:
        return next(i for i in zones if domain.endswith(i.name))

    def mappings_to_zones(self, *domains: str) -> dict[str, Zone]:
        return {domain: self._zone_for_domain(domain) for domain in domains}

        # next(i for i in self._accessible_zones() if domain.endswith(i.name))
        pass

    def mke_tunnels(self, mappings: list[Mapping]):
        for mapping in mappings:
            zone = self._zone_for_domain(mapping.domain)
            tunnel = self.client.zero_trust.tunnels.cloudflared.create(
                account_id=zone.account.id,
                name=f"tunnel-for-{mapping.domain}",
                metadata={_tag: True},
            )
            self._create_dns_record(mapping.domain, tunnel.id)

    def fx_mapping(
            self, zones: list[Zone],
            record_list: list[CNAMERecord],
            mapping: Mapping, tunnel_id) -> ConfigIngress:

        zone = self._find_zone(zones, mapping.domain)
        record: CNAMERecord = record_list
        self._create_dns_record(
            zone_id=zone.id, record_id=record.id, domain=mapping.domain, tunnel_id=tunnel_id)

        return ConfigIngress(
            hostname=mapping.domain,
            service=mapping.service.unicode_string(),
        )

    def tunnel(self, *mappings: Mapping):
        self.fx2()

        # config: Config = {
        #     "ingress": [
        #         ConfigIngress(  # final fallback rule — NO hostname or path allowed
        #             service="http_status:404"
        #         )
        #     ]
        # }

        zones = self._accessible_zones()
        record_list = self.client.dns.records.list(
            zone_id=zone.id).result

        config: Config = {
            "ingress": [
                *(
                    ConfigIngress(
                        hostname=mapping.domain,
                        service=mapping.service.unicode_string(),
                    )
                    for mapping in mappings if not print(mapping)
                ),
                ConfigIngress(service="http_status:404")  # default fallback
            ]
        }

        zones = self._accessible_zones()
        for mapping in mappings:
            zone = self._find_zone(zones, mapping.domain)

        pass
