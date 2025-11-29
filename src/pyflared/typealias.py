from collections import defaultdict

from cloudflare.types.dns import record_batch_params
from cloudflare.types.zones import Zone

Domain = str
Service = str
Mappings = dict[Domain, Service]

ZoneId = str
ZoneName = str
ZoneNames = set[ZoneName]
ZoneNameDict = dict[ZoneName, Zone]

TunnelId = str
TunnelIds = set[TunnelId]

CreationRecords = defaultdict[ZoneId, list[record_batch_params.CNAMERecordParam]]
