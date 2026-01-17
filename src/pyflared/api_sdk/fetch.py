from cloudflare import AsyncCloudflare

from pyflared.shared.types import AccountIds, ZoneIds


async def fetch_zones_account_ids(async_cf: AsyncCloudflare) -> tuple[ZoneIds, AccountIds]:
    zone_ids = ZoneIds()
    account_ids = AccountIds()
    async for zone in async_cf.zones.list():
        zone_ids.add(zone.id)
        account_ids.add(zone.account.id)

    return zone_ids, account_ids
