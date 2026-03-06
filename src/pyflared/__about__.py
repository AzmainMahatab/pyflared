# SPDX-FileCopyrightText: 2026-present Azmain <azmainmahatab012@gmail.com>
#
# SPDX-License-Identifier: MIT
__version__ = "0.1.0-beta7"  # x-release-please-version

from importlib.metadata import metadata

DIST_METADATA = metadata(__package__)
# VERSION = DIST_METADATA["Version"]
AUTHOR = DIST_METADATA["Author"]
PACKAGE_NAME = DIST_METADATA["Name"]
