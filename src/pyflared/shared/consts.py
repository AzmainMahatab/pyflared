import sys
from typing import Final

IS_WINDOWS = sys.platform == "win32"

tags: Final[str] = "tags"
api_managed_tag: Final[str] = "pyflared-managed"
ephemeral: Final[str] = "ephemeral"

cfargotunnel: Final[str] = ".cfargotunnel.com"

CF_API_TOKEN: Final[str] = "CLOUDFLARE_API_TOKEN"
