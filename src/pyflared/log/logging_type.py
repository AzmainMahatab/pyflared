from typing import TypedDict, Optional, Any


# class FormatterConfig(TypedDict):
#     format: str
#     datefmt: Optional[str]
#
#
# class HandlerConfig(TypedDict, total=False):
#     class_: str  # 'class' is a reserved keyword, so we use string key or alias logic if needed.
#     # In TypedDict we often have to use syntax like "class": ... inside the dict definition
#     # or standard dict syntax. See implementation below.
#     level: str
#     formatter: str
#     filename: Optional[str]
#     mode: Optional[str]
#     stream: Optional[str]
#     maxBytes: Optional[int]
#     backupCount: Optional[int]
#
#
# class LoggerConfig(TypedDict, total=False):
#     handlers: list[str]
#     level: str
#     propagate: bool
#
#
# class LoggingConfig(TypedDict):
#     version: int
#     disable_existing_loggers: bool
#     formatters: dict[str, FormatterConfig]
#     handlers: dict[str, HandlerConfig | dict[str, Any]]  # Loose typing for specific handler args
#     loggers: dict[str, LoggerConfig]
#     root: Optional[LoggerConfig]

class FormatterConfig(TypedDict, total=False):
    format: str
    datefmt: Optional[str]


class HandlerConfig(TypedDict, total=False):
    class_: str
    level: str
    formatter: Optional[str]
    filename: Optional[str]
    mode: Optional[str]
    maxBytes: Optional[int]
    backupCount: Optional[int]
    encoding: Optional[str]
    markup: Optional[bool]
    show_path: Optional[bool]
    rich_tracebacks: Optional[bool]


class LoggerConfig(TypedDict, total=False):
    handlers: list[str]
    level: str
    propagate: bool


class LoggingConfig(TypedDict):
    version: int
    disable_existing_loggers: bool
    formatters: dict[str, FormatterConfig]
    handlers: dict[str, HandlerConfig | dict[str, Any]]
    loggers: dict[str, LoggerConfig]
