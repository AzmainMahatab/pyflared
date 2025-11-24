from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class LogSource(Enum):
    STDOUT = "OUT"
    STDERR = "ERR"



@dataclass(frozen=True)
class ProcessEvent(ABC):
    """
    Base event class for all process outputs.
    frozen=True makes it immutable and thread-safe.
    """
    line: str
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        return self.line


@dataclass(frozen=True)
class StdOut(ProcessEvent):
    """Event representing standard output (Info/Logs)."""
    pass


@dataclass(frozen=True)
class StdErr(ProcessEvent):
    """Event representing standard error (Warnings/Errors)."""
    pass
