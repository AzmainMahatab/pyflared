from typing import TypedDict

from cloudflare import Cloudflare
from cloudflare.types import CloudflareTunnel
from cloudflare.types.accounts import Account
from cloudflare.types.dns.record_response import CNAMERecord
from cloudflare.types.zones import Zone, zone_list_params
from pydantic.dataclasses import dataclass

# @dataclass
# class CNAMERecords:
#     records: list[CNAMERecord]
#     zone: Zone
# class CNAMERecords(TypedDict):
#     zone: Zone
#     records: list[CNAMERecord]

ZoneRecords = dict[str, list[CNAMERecord]]


class TunnelManager:
    def __init__(self, api_token: str):
        self.client = Cloudflare(api_token=api_token)

    def all_accounts(self) -> list[Account]:
        return self.client.accounts.list().result

    def account_zones(self, account_id: str) -> list[Zone]:
        return self.client.zones.list(
            account=zone_list_params.Account(id=account_id)).result

    def all_tunnels(self) -> list[CloudflareTunnel]:
        tunnels = []
        for account in self.all_accounts():
            tunnels.extend(self.client.zero_trust.tunnels.cloudflared.list(
                account_id=account.id).result)
        return tunnels

    def all_zones(self) -> list[Zone]:
        return self.client.zones.list().result

    def zone_cname_records(self, zone_id: str) -> list[CNAMERecord]:
        return self.client.dns.records.list(zone_id=zone_id, type="CNAME").result

    def all_cname_records(self) -> ZoneRecords:
        records: ZoneRecords = {}
        for zone in self.all_zones():
            records[zone.id] = self.client.dns.records.list(zone_id=zone.id, type="CNAME").result
        return records

    def delete_tunnel(self, tunnel: CloudflareTunnel):
        self.client.zero_trust.tunnels.cloudflared.delete(
            account_id=tunnel.account.id,
            tunnel_id=tunnel.id
        )

    def delete_record(self, zone_id: str, record_id: str):
        self.client.dns.records.delete(
            zone_id=zone_id,
            dns_record_id=record_id,
        )

    def
