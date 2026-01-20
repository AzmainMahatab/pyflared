import sys
from typing import Final

IS_WINDOWS = sys.platform == "win32"

api_managed_tag: Final[str] = "pyflared-managed"
cfargotunnel: Final[str] = ".cfargotunnel.com"
