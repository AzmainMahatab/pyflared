import platform
import shelve
import shutil
import tarfile
from abc import ABC
from functools import cache
from pathlib import Path
import requests
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.metadata.plugin.interface import MetadataHookInterface
from packaging.tags import platform_tags

base_url = "https://github.com/cloudflare/cloudflared/releases/download"
api = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"


class CloudFlareBinaryInterface(ABC):

    @property
    def ext(self) -> str:
        return ""

    def is_tgz(self):
        return self.ext == ".tar.gz"

    @property
    def asset_name(self):
        system = platform.system().lower()
        machine = platform.machine().lower()
        return f"cloudflared-{system}-{machine}{self.ext}"


tgz = ".tar.gz"
exe = ".exe"


class CloudFlareBinary:
    def __init__(self, version: str) -> None:
        self.version = version

        name = "cloudflared"
        system = platform.system().lower()
        machine = platform.machine().lower()
        ext = {
            "darwin": tgz,
            "windows": exe,
        }.get(system, "")

        self.is_tgz = ext == tgz
        self.asset_name = f"{name}-{system}-{machine}{ext}"
        self.link = f"{base_url}/{self.version}/{self.asset_name}"

        self.final_binary_name = f"{name}{ext}"


@cache
def _binary_version() -> str:
    response = requests.get(api)
    response.raise_for_status()
    return response.json()["tag_name"]


class MetadataHook(MetadataHookInterface):
    def update(self, metadata):
        wrapper_version = self.config.get("wrapper_version", 0)
        binary_version = _binary_version()
        metadata["version"] = f"{binary_version}.{wrapper_version}"


class BuildHook(BuildHookInterface):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.build_dir = Path(self.root) / ".hatch"
        self.download_dir = self.build_dir / "downloads"
        self.binary_dir = self.build_dir / "binary"

    def initialize(self, version: str, build_data: dict) -> None:
        build_data["tag"] = f"py3-none-{list(platform_tags())[-1]}"  # Maximum compatibility since binary is static

        if self.target_name != "wheel":
            return

        binary_version = _binary_version()
        cb = CloudFlareBinary(binary_version)

        self._prepare_dirs()
        self._stage_downloads(cb)
        self._copy_extract(cb)
        self._link_binary(build_data, cb)

    def _prepare_dirs(self) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.binary_dir.mkdir(parents=True, exist_ok=True)

    def _stage_downloads(self, cb: CloudFlareBinary):
        # package_version = self.metadata.core.version
        # binary_name, is_tgz = _binary_name()

        # Enable caching
        # requests_cache.install_cache(_relative_file('http_cache'), cache_control=True)

        etag_file = self.download_dir / "etag"
        with shelve.open(etag_file) as db:
            if old_etag := db.get(cb.link):
                headers = {"If-None-Match": old_etag}
            else:
                headers = {}

        # Download file
        response = requests.get(cb.link, headers=headers, stream=True)

        if response.status_code == 304:
            print(f"Reusing cached {cb.asset_name}")
        else:
            response.raise_for_status()
            download_file = self.download_dir / cb.asset_name
            with open(download_file, "wb") as f:
                print(f"Downloading {cb.asset_name}")
                f.write(response.content)
            if etag := response.headers.get("ETag"):
                with shelve.open(etag_file) as db: db[cb.link] = etag

    def _copy_extract(self, cb: CloudFlareBinary) -> None:
        downloaded_file = self.download_dir / cb.asset_name
        if cb.is_tgz:
            with tarfile.open(downloaded_file) as tar:
                print(f"Extracting {cb.asset_name}")
                tar.extractall(self.binary_dir)
        else:
            final_binary = self.binary_dir / cb.final_binary_name
            shutil.copy(downloaded_file, final_binary)

    def _link_binary(self, build_data: dict, cb: CloudFlareBinary) -> None:
        final_binary = self.binary_dir / cb.final_binary_name
        build_data["force_include"][final_binary] = f"{self.metadata.name}/bin/{cb.final_binary_name}"

    def clean(self, versions: list[str]) -> None:
        try:
            shutil.rmtree(self.build_dir)
            print(f"Cleaned build directory")
        except FileNotFoundError:
            print(f"Build directory not found, nothing to clean")
