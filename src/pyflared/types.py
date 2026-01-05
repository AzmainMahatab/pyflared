import asyncio
import datetime
import os
from collections import defaultdict
from collections.abc import Iterable, Awaitable
from enum import StrEnum, auto
from typing import NamedTuple, Callable

from cloudflare.types.dns import record_batch_params
from cloudflare.types.zones import Zone

type AwaitableMaybe[T] = T | Awaitable[T]

type Domain = str
type Service = str
type ProcessArgs = tuple[str, ...]

type ZoneId = str
type ZoneName = str


class ZoneNames(set[ZoneName]):
    pass


class Mappings(dict[Domain, Service]):
    pass


class ZoneNameDict(dict[ZoneName, Zone]):
    pass


type TunnelId = str


class TunnelIds(set[TunnelId]):
    pass


class CreationRecords(defaultdict[ZoneId, list[record_batch_params.CNAMERecordParam]]):
    pass


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
    timestamp: datetime.datetime = datetime.datetime.now(datetime.UTC)


type CmdArg = str | bytes | os.PathLike[str] | os.PathLike[bytes]
type CmdArgs = AwaitableMaybe[Iterable[CmdArg] | CmdArg]
type CmdTargetable[**P] = Callable[P, CmdArgs]
# type CmdTargetable[**P] = Callable[P, CmdArgs]

type Guard = Callable[[], AwaitableMaybe[bool]]
type ChunkR = AwaitableMaybe[bytes | ChunkSignal]
type StreamChunker = Callable[[asyncio.StreamReader, OutputChannel], ChunkR]
type Response = bytes | str | None
type Responder = Callable[[bytes, OutputChannel], AwaitableMaybe[Response]]

type ProcessOutputFilter = Callable[[ProcessOutput], ProcessOutput | None]

# def get_resolved_return_type(func: Callable[..., Any]) -> Any:
#     """
#     Robustly resolves and returns the return type hint of a function.
#     Handles PEP 563 (string annotations) safely.
#     """
#     try:
#         resolve_pep563(func)
#         # 1. robust resolution
#         resolve_pep563(func)
#     except Exception:
#         # If resolution fails (e.g., missing imports), fallback to Any or log warning
#         # get_type_hints would have just crashed your app here.
#         return Any
#
#     # 2. safe retrieval
#     return func.__annotations__.get('return', Any)
#
#
# import types
# from typing import get_origin, get_args, Any, Union
# from beartype.peps import resolve_pep563
#
#
# # --- Traceable Compatibility Checker ---
# def is_compatible_debug(actual: Any, allowed: Any, depth=0) -> bool:
#     indent = "  " * depth
#     print(f"{indent}❓ Compare: Actual='{actual}' vs Allowed='{allowed}'")
#
#     # 1. Unwrap PEP 695 'type' Aliases
#     if hasattr(allowed, "__value__"):
#         print(f"{indent}  -> Unwrapping Allowed Alias '{allowed}'")
#         return is_compatible_debug(actual, allowed.__value__, depth)
#     if hasattr(actual, "__value__"):
#         print(f"{indent}  -> Unwrapping Actual Alias '{actual}'")
#         return is_compatible_debug(actual.__value__, allowed, depth)
#
#     # 2. Check Any (The most common culprit)
#     if allowed is Any:
#         print(f"{indent}  ✅ Match: Allowed is Any")
#         return True
#
#     # NOTE: We print this to see if your return hint somehow became Any
#     if actual is Any:
#         print(f"{indent}  ⚠️ Match: Actual is Any (Did resolution fail?)")
#         return True
#
#         # 3. Direct Match
#     if actual is allowed:
#         print(f"{indent}  ✅ Match: Identical types")
#         return True
#
#     # 4. Handle Unions
#     allowed_origin = get_origin(allowed)
#     actual_origin = get_origin(actual)
#
#     # Check if allowed is a Union (typing.Union or |)
#     if allowed_origin is Union or allowed_origin is types.UnionType:
#         print(f"{indent}  -> Allowed is Union. Checking options...")
#         for i, arg in enumerate(get_args(allowed)):
#             print(f"{indent}    [Option {i}] Checking '{arg}'...")
#             if is_compatible_debug(actual, arg, depth + 1):
#                 print(f"{indent}  ✅ Match: Found valid option in Union")
#                 return True
#         print(f"{indent}  ❌ Fail: No options in Union matched")
#         return False
#
#     # 5. Handle Generics
#     if allowed_origin and actual_origin:
#         print(f"{indent}  -> Checking Generics '{actual_origin}' vs '{allowed_origin}'")
#         try:
#             if not issubclass(actual_origin, allowed_origin):
#                 if actual_origin is not allowed_origin:
#                     print(f"{indent}  ❌ Fail: Origin mismatch")
#                     return False
#         except TypeError:
#             pass  # Continue checking
#
#         actual_args = get_args(actual)
#         allowed_args = get_args(allowed)
#
#         if not allowed_args:
#             print(f"{indent}  ✅ Match: Allowed is generic (e.g. Iterable)")
#             return True
#
#         if not actual_args:
#             print(f"{indent}  ✅ Match: Actual is generic (e.g. list)")
#             return True
#
#         # Compare contents
#         for i, (act, allw) in enumerate(zip(actual_args, allowed_args)):
#             if not is_compatible_debug(act, allw, depth + 1):
#                 print(f"{indent}  ❌ Fail: Generic argument {i} mismatch")
#                 return False
#         print(f"{indent}  ✅ Match: All generic arguments match")
#         return True
#
#     # 6. Simple Classes
#     try:
#         if issubclass(actual, allowed):
#             print(f"{indent}  ✅ Match: issubclass('{actual}', '{allowed}')")
#             return True
#     except TypeError:
#         pass  # Not a class
#
#     print(f"{indent}  ❌ Fail: exhausted all checks")
#     return False
#
#
# # --- The Validator Wrapper ---
# def validate_return_type(func, target_type):
#     print(f"\n--- DEBUG START: {func.__name__} ---")
#
#     # 1. Resolve
#     try:
#         resolve_pep563(func)
#     except Exception as e:
#         print(f"🚨 Resolution Error: {e}")
#
#     # 2. Get Hint
#     return_hint = func.__annotations__.get('return', Any)
#     print(f"📝 Resolved Return Hint: {return_hint}")
#
#     # 3. Check
#     if not is_compatible_debug(return_hint, target_type):
#         print("💥 CHECK FAILED (As expected)")
#         raise TypeError(f"Expected {target_type}, got {return_hint}")
#     else:
#         print("🟢 CHECK PASSED (Unexpectedly!)")
