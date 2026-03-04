import asyncio
import os
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable, AsyncGenerator
from dataclasses import field, dataclass
from enum import StrEnum, auto
from typing import NamedTuple

from cloudflare.types.dns import record_batch_params, RecordBatchResponse, RecordResponse
from cloudflare.types.dns.batch_patch_param import BatchPatchParam
from cloudflare.types.dns.batch_put_param import BatchPutParam
from cloudflare.types.zones import Zone

from pyflared.core.model import ZoneEntry

# type IterableMaybe[T] = Iterable[T] | T
#
#
# def to_iterable[T](a: IterableMaybe[T]) -> Iterable[T]:
#     return a if isinstance(a, Iterable) else (a,)

# class DataSet[D, T](set[T]):
#     def __init__(self, data: D, iterable: Iterable[T] | None = None) -> None:
#         """
#         Initializes the DataSet.
#
#         Parameters:
#         - data (D): The additional payload/data you want to store alongside the set elements.
#                     It is bound to the generic type `D`.
#         - iterable (Iterable[T] | None): An optional iterable containing the initial elements
#                                          to populate the set. It defaults to None to allow
#                                          creating an empty set.
#         """
#         # Initialize the parent class (set) with or without the initial iterable
#         if iterable is not None:
#             super().__init__(iterable)
#         else:
#             super().__init__()
#
#         # Store the extra data internally
#         self.data: D = data


type AwaitableMaybe[T] = T | Awaitable[T]

type Cname = str
# type Service = str
type ProcessArgs = tuple[str, ...]

type ZoneId = str
type ZoneName = str
type RecordName = str


class ZoneIds(set[ZoneId]):
    pass


class ZoneNames(set[ZoneName]):
    pass


class CnameRecordNames(set[RecordName]):
    pass


# type AccountId = str
#
# type AccountIds = set[AccountId]

# class AccountIds(set[AccountId]):
#     pass


# class Mappings(dict[Domain, Service]):
#     pass


class ZoneNameDict(dict[ZoneName, Zone]):
    pass


type TunnelId = str


class TunnelIds(set[TunnelId]):
    pass


class CreationRecords(defaultdict[ZoneId, list[record_batch_params.Post]]):
    def __init__(self):
        # Explicitly pass 'list' to the parent constructor
        super().__init__(list)


def to_delete_param(response: RecordResponse) -> record_batch_params.Delete:
    return record_batch_params.Delete(id=response.id)


@dataclass
class RecordBatchParam:
    # zone_id: str
    zone: ZoneEntry
    creates: list[record_batch_params.Post] = field(default_factory=list)
    deletes: list[record_batch_params.Delete] = field(default_factory=list)
    replace: list[BatchPutParam] = field(default_factory=list)
    edit: list[BatchPatchParam] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.creates or self.deletes or self.replace or self.edit)

    # @classmethod
    # def from_response(cls, r: RecordBatchResponse) -> RecordBatchParam:
    #     return RecordBatchParam(r)


def delify_response(zone: ZoneEntry, r: RecordBatchResponse) -> RecordBatchParam:
    posts2 = [to_delete_param(response) for response in r.posts or []]
    puts2 = [to_delete_param(response) for response in r.puts or []]
    patches2 = [to_delete_param(response) for response in r.patches or []]
    return RecordBatchParam(zone, deletes=posts2 + puts2 + patches2)


# class RecordBatchParamDict(defaultdict[str, RecordBatchParam]):
#     def __init__(self) -> None:
#         super().__init__(RecordBatchParam)


# class RecordBatchResponseDict(defaultdict[str, RecordBatchResponse]):
#     def __init__(self) -> None:
#         super().__init__(RecordBatchResponse)
#
#     def delify(self) -> RecordBatchParamDict:
#         param = RecordBatchParamDict()
#         for zone_id, v in self.items():
#             posts2 = [to_delete_param(response) for response in v.posts or []]
#             puts2 = [to_delete_param(response) for response in v.puts or []]
#             patches2 = [to_delete_param(response) for response in v.patches or []]
#
#             param[zone_id].deletes = posts2 + puts2 + patches2
#
#         return param


class CommandError(Exception):
    pass


class OutputChannel(StrEnum):
    STDOUT = auto()
    STDERR = auto()


class ChunkSignal(StrEnum):
    EOF = auto()
    SKIP = auto()


class ProcessOutput(NamedTuple):
    data: bytes
    channel: OutputChannel
    # timestamp: datetime.datetime = datetime.datetime.now(datetime.UTC)


type CmdArg = str | bytes | os.PathLike[str] | os.PathLike[bytes]
type CmdArgs = Iterable[CmdArg] | CmdArg
type ProcessCmd = Awaitable[CmdArgs] | AsyncGenerator[CmdArgs, None] | CmdArgs

type BinaryCallable = Callable[[], CmdArg]

type Guard = Callable[[], AwaitableMaybe[bool]]
type Chunk = bytes | ChunkSignal
type StreamChunker = Callable[[asyncio.StreamReader, OutputChannel], AwaitableMaybe[Chunk]]
type Response = bytes | str | None
type Responder = Callable[[bytes, OutputChannel], AwaitableMaybe[Response]]

type ProcessOutputFilter = Callable[[ProcessOutput], ProcessOutput | None]
