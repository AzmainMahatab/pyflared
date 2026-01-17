import hashlib
import logging
import platform
import shutil
import tarfile
from functools import cached_property
from pathlib import Path
from typing import Any

import httpx
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from klepto.archives import dir_archive
from packaging.tags import platform_tags
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console(stderr=True)

base_url = "https://github.com/cloudflare/cloudflared/releases/download"
cloudflared_gh_api = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"

tgz = ".tar.gz"


class CloudFlareBinary:
    def __init__(self, version: str) -> None:
        self.version = version

        name = "cloudflared"
        system = platform.system().lower()
        arch = platform.machine().lower()

        # --- FIX START: Map Python arch to Cloudflare arch ---
        arch_map = {
            "x86_64": "amd64",
            "aarch64": "arm64",
            "armv7l": "arm",
        }
        # Use the mapped value or default to the original if not found
        arch = arch_map.get(arch, arch)
        # --- FIX END ---

        ext = {
            "darwin": tgz,
            "windows": ".exe",
        }.get(system, "")

        self.is_tgz = ext == tgz
        self.asset_name = f"{name}-{system}-{arch}{ext}"
        self.final_binary_name = f"{name}{ext}"

    @property
    def link(self):
        return f"{base_url}/{self.version}/{self.asset_name}"


class BuildHook(BuildHookInterface):

    @cached_property
    def build_dir(self) -> Path:
        return Path(self.root) / ".hatch"

    @cached_property
    def download_dir(self) -> Path:
        return self.build_dir / "downloads"

    @cached_property
    def binary_dir(self) -> Path:
        return self.build_dir / "binary"

    @cached_property
    def cache_dir(self) -> Path:
        return self.build_dir / "cache"

    def ensure_dirs(self) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.binary_dir.mkdir(parents=True, exist_ok=True)

    @cached_property
    def cache_db(self):
        return dir_archive(self.cache_dir, cached=False)

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        build_data["tag"] = f"py3-none-{list(platform_tags())[-1]}"  # Maximum compatibility since binary is static

        if self.target_name != "wheel":
            return

        self.ensure_dirs()
        with httpx.Client(follow_redirects=True) as client:
            cloudflare_binary = self._stage_downloads(client)

        self._copy_extract(cloudflare_binary)
        self._link_binary(build_data, cloudflare_binary)

    @cached_property
    def file_binary_version(self) -> str:
        version_file = Path(self.root) / "cloudflared.version"
        if version_file.is_file() and (content := version_file.read_text("utf-8").strip()):
            return content
        return "latest"

    def binary_version(self, client: httpx.Client) -> str:
        version = self.file_binary_version
        if version == "latest":
            version = self.current_latest(client)
        return version

    @classmethod
    def current_latest(cls, client: httpx.Client) -> str:
        response = client.get(cloudflared_gh_api)
        response.raise_for_status()
        return response.json()["tag_name"]

    def _stage_downloads(self, client: httpx.Client) -> CloudFlareBinary:
        version = self.binary_version(client)
        cloudflared_binary = CloudFlareBinary(version)

        key = hashlib.md5(cloudflared_binary.link.encode(), usedforsecurity=False).hexdigest()

        # No 'with' block needed. db.get() reads directly from the disk.
        if old_etag := self.cache_db.get(key):
            headers = {"If-None-Match": old_etag}
        else:
            headers = {}

        # Download file
        response = client.get(cloudflared_binary.link, headers=headers)

        if response.status_code == httpx.codes.NOT_MODIFIED:
            console.print(f"Reusing cached {cloudflared_binary.asset_name}")
        else:
            response.raise_for_status()
            download_file = self.download_dir / cloudflared_binary.asset_name
            with open(download_file, "wb") as file:
                logger.info(f"Downloading {cloudflared_binary.asset_name}")
                file.write(response.content)

            # Save: Writes happen immediately because cached=False
            if etag := response.headers.get("ETag"):
                self.cache_db[key] = etag

        return cloudflared_binary

    def _copy_extract(self, cloudflared_binary: CloudFlareBinary) -> None:
        downloaded_file = self.download_dir / cloudflared_binary.asset_name
        if cloudflared_binary.is_tgz:
            with tarfile.open(downloaded_file) as tar:
                logger.info(f"Extracting {cloudflared_binary.asset_name}")
                tar.extractall(self.binary_dir)
        else:
            final_binary = self.binary_dir / cloudflared_binary.final_binary_name
            shutil.copy(downloaded_file, final_binary)

    def _link_binary(self, build_data: dict, cloudflared_binary: CloudFlareBinary) -> None:
        final_binary = self.binary_dir / cloudflared_binary.final_binary_name
        build_data["force_include"][
            final_binary] = f"{self.metadata.name}/bin/{cloudflared_binary.final_binary_name}"

    # Clean is not fully correct for now, hopping it to be fixed on the hatch side
    # https://github.com/pypa/hatch/issues/2147
    def clean(self, versions: list[str]) -> None:
        try:
            shutil.rmtree(self.build_dir)
            logger.info("Cleaned build directory")
        except FileNotFoundError:
            logger.info("Build directory not found, nothing to clean")
