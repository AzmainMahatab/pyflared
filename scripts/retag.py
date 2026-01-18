# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "packaging",
# ]
# ///

"""Retag generic linux wheels to manylinux and musllinux variants.

This script takes wheels with `linux_*` platform tags and creates
properly tagged variants for PyPI:
- manylinux_2_17_* (glibc-based systems)
- musllinux_1_1_* (musl-based systems like Alpine)

Since cloudflared is a static Go binary, the same binary works on both.
"""

import base64
import csv
import hashlib
import io
import sys
import zipfile
from pathlib import Path

from packaging.utils import parse_wheel_filename


def compute_hash_digest(data: bytes) -> str:
    """Compute the hash digest in wheel RECORD format (sha256=base64_urlsafe)."""
    digest = hashlib.sha256(data).digest()
    # URL-safe base64 without padding, as per PEP 376
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def retag_wheel(dist_dir: Path) -> None:
    """Find all generic linux wheels and retag them to manylinux/musllinux."""
    # 1. Find ALL generic linux wheels (x86_64, aarch64, etc.)
    generic_wheels = list(dist_dir.glob("*-linux_*.whl"))

    if not generic_wheels:
        print(f"Error: No generic 'linux_*' wheels found in {dist_dir}")
        sys.exit(1)

    for source_wheel in generic_wheels:
        print(f"Processing: {source_wheel.name}")

        # 2. Parse filename
        name, ver, build, tags = parse_wheel_filename(source_wheel.name)

        # 3. Extract Architecture
        original_tag = next(iter(tags))
        current_plat = original_tag.platform  # e.g. "linux_x86_64"

        if not current_plat.startswith("linux_"):
            raise ValueError(f"Unexpected platform tag: {current_plat}")

        arch = current_plat.split("_", 1)[1]  # "x86_64" or "aarch64"

        # 4. Define Targets dynamically based on arch
        target_platforms = [
            f"manylinux_2_17_{arch}",
            f"musllinux_1_1_{arch}",
        ]

        for new_plat in target_platforms:
            build_tag = f"-{build[0]}{build[1]}" if build else ""
            new_filename = f"{name}-{ver}{build_tag}-{original_tag.interpreter}-{original_tag.abi}-{new_plat}.whl"
            dest_path = dist_dir / new_filename

            print(f"  -> Creating: {new_filename}")

            # 5. Copy & Update Metadata, track modified files for RECORD
            modified_files: dict[str, tuple[str, int]] = {}  # filename -> (hash, size)
            dist_info_dir: str | None = None

            with (
                zipfile.ZipFile(source_wheel, "r") as src,
                zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as dst,
            ):
                for item in src.infolist():
                    content = src.read(item.filename)

                    # Track the dist-info directory name
                    if ".dist-info/" in item.filename and dist_info_dir is None:
                        dist_info_dir = item.filename.split("/")[0]

                    # Update WHEEL file with new platform tag
                    if item.filename.endswith(".dist-info/WHEEL"):
                        text = content.decode("utf-8")
                        if current_plat not in text:
                            raise RuntimeError(
                                f"Metadata mismatch: Filename has {current_plat} but WHEEL file does not."
                            )
                        text = text.replace(current_plat, new_plat)
                        content = text.encode("utf-8")

                    # Skip RECORD - we'll regenerate it
                    if item.filename.endswith(".dist-info/RECORD"):
                        continue

                    # Write file and track hash/size
                    dst.writestr(item, content)
                    modified_files[item.filename] = (compute_hash_digest(content), len(content))

                # 6. Generate new RECORD file
                if dist_info_dir:
                    record_path = f"{dist_info_dir}/RECORD"
                    record_content = io.StringIO()
                    writer = csv.writer(record_content)

                    for filename, (hash_digest, size) in sorted(modified_files.items()):
                        writer.writerow([filename, hash_digest, size])

                    # RECORD itself is listed without hash (per PEP 376)
                    writer.writerow([record_path, "", ""])

                    record_bytes = record_content.getvalue().encode("utf-8")
                    dst.writestr(record_path, record_bytes)

        # 7. Cleanup source wheel
        source_wheel.unlink()
        print(f"  -> Removed source: {source_wheel.name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/retag.py <dist_dir>")
        sys.exit(1)

    retag_wheel(Path(sys.argv[1]))
