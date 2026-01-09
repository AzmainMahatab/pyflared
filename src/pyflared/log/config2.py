import logging
import sys
from pathlib import Path
from typing import Final, TYPE_CHECKING

from loguru import logger
from platformdirs import user_log_dir

from pyflared.shared.contants import APP_NAME, AUTHOR

if TYPE_CHECKING:
    from loguru import Record

CONSOLE_DEFAULT_LEVEL = logging.INFO

CONTEXT_MIN_LEVEL: Final[str] = "min_level"


def console_filter(record: "Record") -> bool:
    """
    Filter logic using integer comparison only.
    """
    # 1. Extract level (Record.level is a generic object, but we know it has .no)
    # We cast or access safely. Loguru's Record 'level' attribute has a 'no' property.
    current_level_no: int = record["level"].no

    # 2. Extract context override
    # Record["extra"] returns a dict, so .get() is valid
    context_level_no: int | None = record["extra"].get(CONTEXT_MIN_LEVEL)

    if context_level_no is not None:
        return current_level_no >= context_level_no

    return current_level_no >= CONSOLE_DEFAULT_LEVEL


def isolated_logging(level: int = logging.DEBUG):
    """
    Context manager that uses the shared Constant Key.
    """
    # kwargs unpacking is safe here because we use the constant key
    return logger.contextualize(**{CONTEXT_MIN_LEVEL: level})


logger.remove()

# SINK 1: Console
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level=logging.NOTSET,
    filter=console_filter,
    colorize=True
)

log_dir = Path(user_log_dir(APP_NAME, AUTHOR))
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "tunnel.log"

# SINK 2: File
logger.add(
    log_file,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level=logging.DEBUG,
    rotation="10 MB",
    compression="zip"
)
