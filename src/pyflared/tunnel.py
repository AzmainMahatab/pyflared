from datetime import datetime, timezone, timedelta
from typing import Annotated, Iterator

from cloudflare import Cloudflare
from cloudflare.types import CloudflareTunnel
from cloudflare.types.dns import record_list_params
from cloudflare.types.magic_transit.connectors.snapshot_get_response import Tunnel
from cloudflare.types.zones import Zone
from pydantic import HttpUrl, StringConstraints, IPvAnyAddress
from pydantic.dataclasses import dataclass


@dataclass
class Mapping:
    domain: str
    service: HttpUrl


_tag = "pyflared-managed"


def _is_orphan(tunnel: CloudflareTunnel) -> bool:
    # has tag, inactive + time, down
    # now = datetime.now(timezone.utc)
    # threshold = now - timedelta(seconds=5)
    # return tunnel.metadata.get(_tag) and (
    #         (tunnel.status == "inactive" and tunnel.created_at < threshold) or (
    #         tunnel.status == "down" and tunnel.conns_inactive_at and tunnel.conns_inactive_at < threshold)
    # )
    return tunnel.metadata.get(_tag) and tunnel.status in ("inactive", "down")


def _dns_content(tunnel_id: str) -> str:
    return f"{tunnel_id}.cfargotunnel.com"


class TunnelManager:
    def __init__(self, api_token: str):
        self.client = Cloudflare(api_token=api_token)

    def _accessible_zones(self) -> list[Zone]:
        return self.client.zones.list().result

    def _zone_for_domain(self, domain: str) -> Zone:
        return next(i for i in self._accessible_zones() if domain.endswith(i.name))

    def _zone_tunnels(self, zone: Zone) -> list[Tunnel]:
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

    def _make_dns_record(self, domain: str, tunnel_id: str):
        zone = self._zone_for_domain(domain)
        record_list = self.client.dns.records.list(
            zone_id=zone.id,
            name=record_list_params.Name(exact=domain))

        if not record_list.result:
            self.client.dns.records.create(
                zone_id=zone.id,
                name=domain,
                type="CNAME",
                content=_dns_content(tunnel_id),
                proxied=True,
                comment=_tag,
            )
        else:
            self.client.dns.records.update(
                dns_record_id=record_list.result[0].id,
                zone_id=zone.id,
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

        pass

    def tunnel(self, *mappings: Mapping):
        self._remove_orphans()
        pass
