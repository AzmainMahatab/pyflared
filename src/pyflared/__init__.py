import logging
import sys
import warnings

from loguru import logger

from pyflared.consts import IS_WINDOWS

# Supress Pydantic V1 deprecation warning in cloudflare
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="cloudflare._compat",
)

# Remove the default Loguru handler (which is set to DEBUG by default)
logger.remove()

# Add your "Boot" handler: Simple format, STRICTLY INFO level
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
    level=logging.INFO
)

# Apply monkey patch till my PR is accepted.
import pyflared.api_sdk.monkey_patch  # noqa: F401
from pyflared._commands import binary_path, binary_version, run_dns_fixed_tunnel, run_quick_tunnel, run_token_tunnel

__all__ = [
    "binary_path",
    "binary_version",
    "run_dns_fixed_tunnel",
    "run_quick_tunnel",
    "run_token_tunnel",
]
