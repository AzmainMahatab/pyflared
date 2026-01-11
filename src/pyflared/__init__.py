import logging
import sys
import warnings

from loguru import logger

# Supress Pydantic V1 deprecation warning in cloudflare
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="cloudflare._compat",
)

# 1. Remove the default Loguru handler (which is set to DEBUG by default)
logger.remove()

# 2. Add your "Boot" handler: Simple format, STRICTLY INFO level
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
    level=logging.INFO
)

# Apply monkey patch till my PR is accepted.
import pyflared.sdk.monkey_patch
