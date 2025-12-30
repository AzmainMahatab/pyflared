import hashlib
import platform
import shutil
import tarfile
from functools import cached_property
from pathlib import Path
from typing import Any

import requests
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.metadata.plugin.interface import MetadataHookInterface
from klepto.archives import dir_archive
from packaging.tags import platform_tags

base_url = "https://github.com/cloudflare/cloudflared/releases/download"
api = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"

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
        # Use the mapped value, or default to the original if not found
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


_binary_version = "binary_version"


class _BuildShare:

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # The constraint: The child class (cls) MUST be a subclass of
        # either MetadataHookInterface OR BuildHookInterface.
        required_parents = (MetadataHookInterface, BuildHookInterface)

        if not issubclass(cls, required_parents):
            required_names = " or ".join(c.__name__ for c in required_parents)

            raise TypeError(
                f"'{cls.__name__}' cannot inherit from {__class__.__name__} unless it also inherits from {required_names}."
            )

    @cached_property
    def build_dir(self):
        return Path(self.root) / ".hatch"  # type: ignore # ensured by __init_subclass__

    @cached_property
    def download_dir(self):
        return self.build_dir / "downloads"

    @cached_property
    def binary_dir(self):
        return self.build_dir / "binary"

    @cached_property
    def cache_dir(self):
        return self.build_dir / "cache"

    def ensure_dirs(self):
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.binary_dir.mkdir(parents=True, exist_ok=True)

    @cached_property
    def cache_db(self):
        return dir_archive(self.cache_dir, cached=False)


class MetadataHook(MetadataHookInterface, _BuildShare):

    @cached_property
    def binary_version(self) -> str:
        version = self.config.get(_binary_version, "latest")

        if version == "latest":
            response = requests.get(api)
            response.raise_for_status()
            version = response.json()["tag_name"]

        self.cache_db[_binary_version] = version
        return version

    def update(self, metadata):
        self.ensure_dirs()
        # print(f"R:{self.build_dir}")
        wrapper_version = self.config.get("wrapper_version", 0)
        # print(f"Wrapper version: {wrapper_version}")  # Change to logger

        metadata["version"] = f"{self.binary_version}.{wrapper_version}"
        # print(f"Evaluated version: {metadata["version"]}")


class BuildHook(BuildHookInterface, _BuildShare):
    @cached_property
    def cloudflared_binary(self):
        binary_version = self.cache_db[_binary_version]
        return CloudFlareBinary(binary_version)

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        build_data["tag"] = f"py3-none-{list(platform_tags())[-1]}"  # Maximum compatibility since binary is static

        if self.target_name != "wheel":
            return

        # self.ensure_dirs() #No need as already done in MetadataHook
        self._stage_downloads()
        self._copy_extract()
        self._link_binary(build_data)

    def _stage_downloads(self):

        key = hashlib.md5(self.cloudflared_binary.link.encode()).hexdigest()

        # No 'with' block needed. db.get() reads directly from the disk.
        if old_etag := self.cache_db.get(key):
            headers = {"If-None-Match": old_etag}
        else:
            headers = {}

        # Download file
        response = requests.get(self.cloudflared_binary.link, headers=headers, stream=True)

        if response.status_code == 304:
            pass
            # print(f"Reusing cached {self.cloudflared_binary.asset_name}")
        else:
            response.raise_for_status()
            download_file = self.download_dir / self.cloudflared_binary.asset_name
            with open(download_file, "wb") as file:
                # print(f"Downloading {self.cloudflared_binary.asset_name}")
                file.write(response.content)

            # Save: Writes happen immediately because cached=False
            if etag := response.headers.get("ETag"):
                self.cache_db[key] = etag

    def _copy_extract(self) -> None:
        downloaded_file = self.download_dir / self.cloudflared_binary.asset_name
        if self.cloudflared_binary.is_tgz:
            with tarfile.open(downloaded_file) as tar:
                # print(f"Extracting {self.cloudflared_binary.asset_name}")
                tar.extractall(self.binary_dir)
        else:
            final_binary = self.binary_dir / self.cloudflared_binary.final_binary_name
            shutil.copy(downloaded_file, final_binary)

    def _link_binary(self, build_data: dict) -> None:
        final_binary = self.binary_dir / self.cloudflared_binary.final_binary_name
        build_data["force_include"][
            final_binary] = f"{self.metadata.name}/bin/{self.cloudflared_binary.final_binary_name}"

    # Clean is not fully correct for now, hopping it to be fixed on the hatch side
    # https://github.com/pypa/hatch/issues/2147
    def clean(self, versions: list[str]) -> None:
        try:
            shutil.rmtree(self.build_dir)
            # print(f"Cleaned build directory")
        except FileNotFoundError:
            pass
            # print(f"Build directory not found, nothing to clean")
