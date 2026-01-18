"""Hatch build hook for bundling cloudflared binary into the wheel."""

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
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console(stderr=True)

# =============================================================================
# Constants
# =============================================================================

BINARY_NAME = "cloudflared"
GITHUB_RELEASES_URL = "https://github.com/cloudflare/cloudflared/releases/download"
GITHUB_API_LATEST = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"

# Platform detection (cached at module load)
SYSTEM = platform.system().lower()
MACHINE = platform.machine().lower()

# Architecture mappings
# Python's platform.machine() -> cloudflared release naming
ARCH_TO_CLOUDFLARED = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "arm",
}

# Python's platform.machine() -> wheel platform tag
ARCH_TO_WHEEL = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
    "armv7l": "armv7l",
}


# =============================================================================
# Platform Tag Helper
# =============================================================================


def get_wheel_platform_tag() -> str:
    """Get a PyPI-compatible platform tag for the wheel.

    We hardcode all platform tags for maximum compatibility because cloudflared
    is a static Go binary with NO system library dependencies.
    
    Using platform_tags() would tie compatibility to the build machine's OS version,
    which is not what we want for a static binary.
    
    Platform tags used:
    - Linux: manylinux_2_17 (glibc 2.17, RHEL 7+, Ubuntu 18.04+, Debian 9+)
    - macOS x86_64: macosx_10_9 (oldest commonly supported)
    - macOS arm64: macosx_11_0 (arm64 was introduced in macOS 11)
    - Windows: win_amd64/win32 (no version component needed)
    """
    arch = ARCH_TO_WHEEL.get(MACHINE, MACHINE)
    
    if SYSTEM == "linux":
        return f"manylinux_2_17_{arch}"
    elif SYSTEM == "darwin":
        # arm64 requires macOS 11+, x86_64 can go back to 10.9
        min_version = "11_0" if MACHINE in ("arm64", "aarch64") else "10_9"
        return f"macosx_{min_version}_{arch}"
    elif SYSTEM == "windows":
        return f"win_{arch}"
    else:
        # Fallback for unknown systems
        return f"{SYSTEM}_{arch}"


# =============================================================================
# Cloudflared Binary Descriptor
# =============================================================================


class CloudflaredBinary:
    """Describes the cloudflared binary asset for the current platform."""

    def __init__(self, version: str) -> None:
        self.version = version
        self._arch = ARCH_TO_CLOUDFLARED.get(MACHINE, MACHINE)

        # Determine asset extension and whether it's a tarball
        if SYSTEM == "darwin":
            self._asset_ext = ".tgz"
            self.is_tarball = True
        elif SYSTEM == "windows":
            self._asset_ext = ".exe"
            self.is_tarball = False
        else:  # Linux and others
            self._asset_ext = ""
            self.is_tarball = False

    @property
    def asset_name(self) -> str:
        """Filename of the release asset to download."""
        return f"{BINARY_NAME}-{SYSTEM}-{self._arch}{self._asset_ext}"

    @property
    def final_binary_name(self) -> str:
        """Filename of the binary after extraction (if needed)."""
        ext = ".exe" if SYSTEM == "windows" else ""
        return f"{BINARY_NAME}{ext}"

    @property
    def download_url(self) -> str:
        """Full URL to download the asset."""
        return f"{GITHUB_RELEASES_URL}/{self.version}/{self.asset_name}"


# =============================================================================
# Hatch Build Hook
# =============================================================================


class BuildHook(BuildHookInterface):
    """Hatch build hook that downloads and bundles cloudflared binary."""

    # -------------------------------------------------------------------------
    # Directory Properties
    # -------------------------------------------------------------------------

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

    @cached_property
    def cache_db(self) -> dir_archive:
        return dir_archive(self.cache_dir, cached=False)

    def _ensure_dirs(self) -> None:
        """Create all required build directories."""
        for directory in (self.build_dir, self.download_dir, self.binary_dir):
            directory.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Version Resolution
    # -------------------------------------------------------------------------

    @cached_property
    def _version_from_file(self) -> str:
        """Read pinned version from cloudflared.version file, or 'latest'."""
        version_file = Path(self.root) / "cloudflared.version"
        if version_file.is_file():
            if content := version_file.read_text("utf-8").strip():
                return content
        return "latest"

    def _resolve_version(self, client: httpx.Client) -> str:
        """Resolve the actual version to download."""
        if self._version_from_file == "latest":
            return self._fetch_latest_version(client)
        return self._version_from_file

    @staticmethod
    def _fetch_latest_version(client: httpx.Client) -> str:
        """Fetch the latest release version from GitHub API."""
        response = client.get(GITHUB_API_LATEST)
        response.raise_for_status()
        return response.json()["tag_name"]

    # -------------------------------------------------------------------------
    # Download & Extract
    # -------------------------------------------------------------------------

    def _download_binary(self, client: httpx.Client) -> CloudflaredBinary:
        """Download the cloudflared binary with ETag caching."""
        version = self._resolve_version(client)
        binary = CloudflaredBinary(version)

        # Use URL hash as cache key for ETag storage
        cache_key = hashlib.md5(binary.download_url.encode(), usedforsecurity=False).hexdigest()

        # Check for cached ETag
        headers = {}
        if old_etag := self.cache_db.get(cache_key):
            headers["If-None-Match"] = old_etag

        response = client.get(binary.download_url, headers=headers)

        if response.status_code == httpx.codes.NOT_MODIFIED:
            console.print(f"[green]✓[/] Reusing cached {binary.asset_name}")
        else:
            response.raise_for_status()
            download_path = self.download_dir / binary.asset_name
            download_path.write_bytes(response.content)
            logger.info(f"Downloaded {binary.asset_name}")

            # Cache the ETag for future builds
            if etag := response.headers.get("ETag"):
                self.cache_db[cache_key] = etag

        return binary

    def _extract_binary(self, binary: CloudflaredBinary) -> None:
        """Extract or copy the binary to the binary directory."""
        downloaded_file = self.download_dir / binary.asset_name

        if binary.is_tarball:
            logger.info(f"Extracting {binary.asset_name}")
            with tarfile.open(downloaded_file) as tar:
                tar.extractall(self.binary_dir)
        else:
            final_path = self.binary_dir / binary.final_binary_name
            shutil.copy(downloaded_file, final_path)

    def _include_binary(self, build_data: dict[str, Any], binary: CloudflaredBinary) -> None:
        """Add the binary to the wheel's force_include."""
        final_path = self.binary_dir / binary.final_binary_name
        wheel_path = f"{self.metadata.name}/bin/{binary.final_binary_name}"
        build_data["force_include"][final_path] = wheel_path

    # -------------------------------------------------------------------------
    # Hatch Interface
    # -------------------------------------------------------------------------

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Called by hatch before building."""
        # Set the wheel platform tag
        build_data["tag"] = f"py3-none-{get_wheel_platform_tag()}"

        # Only process wheel builds
        if self.target_name != "wheel":
            return

        self._ensure_dirs()

        with httpx.Client(follow_redirects=True) as client:
            binary = self._download_binary(client)

        self._extract_binary(binary)
        self._include_binary(build_data, binary)

    def clean(self, versions: list[str]) -> None:
        """Clean the build directory.
        
        Note: This is not fully correct for now, hoping it to be fixed on the hatch side.
        See: https://github.com/pypa/hatch/issues/2147
        """
        try:
            shutil.rmtree(self.build_dir)
            logger.info("Cleaned build directory")
        except FileNotFoundError:
            logger.info("Build directory not found, nothing to clean")
