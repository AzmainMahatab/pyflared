# SPDX-FileCopyrightText: 2025-present Azmain <azmainmahatab012@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Pytest suite for fix_ingress_order - input vs expected output tests."""

import pytest
from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import (
    ConfigIngress,
)

from pyflared.api_sdk.ingress import fix_ingress_order, default_catch_all


@pytest.mark.parametrize(
    "input_rules,expected",
    [
        # Empty input → default catch-all only
        pytest.param(
            [],
            [default_catch_all],
            id="empty_input",
        ),
        # Catch-all placed first → moved to last
        pytest.param(
            [
                ConfigIngress(service="http_status:503"),
                ConfigIngress(hostname="example.com", service="http://localhost:8080"),
            ],
            [
                ConfigIngress(hostname="example.com", service="http://localhost:8080"),
                ConfigIngress(service="http_status:503"),
            ],
            id="catch_all_first_moved_to_last",
        ),
        # Paths out of order → sorted longest first
        pytest.param(
            [
                ConfigIngress(hostname="example.com", path="/api", service="http://a:8000"),
                ConfigIngress(hostname="example.com", path="/api/v2/users", service="http://b:9000"),
                ConfigIngress(hostname="example.com", path="/api/v2", service="http://c:9001"),
            ],
            [
                ConfigIngress(hostname="example.com", path="/api/v2/users", service="http://b:9000"),
                ConfigIngress(hostname="example.com", path="/api/v2", service="http://c:9001"),
                ConfigIngress(hostname="example.com", path="/api", service="http://a:8000"),
                default_catch_all,
            ],
            id="paths_sorted_by_specificity",
        ),
        # Root rules unordered → sorted alphabetically
        pytest.param(
            [
                ConfigIngress(hostname="zoo.com", service="http://zoo:3000"),
                ConfigIngress(hostname="alpha.com", service="http://alpha:1000"),
                ConfigIngress(hostname="beta.com", service="http://beta:2000"),
            ],
            [
                ConfigIngress(hostname="alpha.com", service="http://alpha:1000"),
                ConfigIngress(hostname="beta.com", service="http://beta:2000"),
                ConfigIngress(hostname="zoo.com", service="http://zoo:3000"),
                default_catch_all,
            ],
            id="hostnames_sorted_alphabetically",
        ),
        # Mixed: paths + roots + catch-all all jumbled
        pytest.param(
            [
                ConfigIngress(service="http_status:503"),
                ConfigIngress(hostname="zoo.com", service="http://zoo:3000"),
                ConfigIngress(hostname="example.com", path="/api/v2", service="http://b:9000"),
                ConfigIngress(hostname="alpha.com", service="http://alpha:1000"),
                ConfigIngress(hostname="example.com", path="/api", service="http://a:8000"),
            ],
            [
                ConfigIngress(hostname="example.com", path="/api/v2", service="http://b:9000"),
                ConfigIngress(hostname="example.com", path="/api", service="http://a:8000"),
                ConfigIngress(hostname="alpha.com", service="http://alpha:1000"),
                ConfigIngress(hostname="zoo.com", service="http://zoo:3000"),
                ConfigIngress(service="http_status:503"),
            ],
            id="mixed_paths_roots_catchall",
        ),
        # Missing catch-all → default added
        pytest.param(
            [
                ConfigIngress(hostname="example.com", service="http://localhost:8080"),
            ],
            [
                ConfigIngress(hostname="example.com", service="http://localhost:8080"),
                default_catch_all,
            ],
            id="missing_catchall_adds_default",
        ),
        # Path rules before root rules
        pytest.param(
            [
                ConfigIngress(hostname="example.com", service="http://root:80"),
                ConfigIngress(hostname="example.com", path="/api", service="http://api:8000"),
            ],
            [
                ConfigIngress(hostname="example.com", path="/api", service="http://api:8000"),
                ConfigIngress(hostname="example.com", service="http://root:80"),
                default_catch_all,
            ],
            id="paths_before_roots",
        ),
    ],
)
def test_fix_ingress_order(input_rules: list[ConfigIngress], expected: list[ConfigIngress]) -> None:
    """Test that fix_ingress_order produces expected output for various inputs."""
    result = fix_ingress_order(input_rules)
    assert result == expected


def test_multiple_catch_all_raises() -> None:
    """Multiple catch-all rules should raise ValueError."""
    input_rules = [
        ConfigIngress(service="http_status:404"),
        ConfigIngress(service="http_status:503"),
    ]
    with pytest.raises(ValueError, match=r"Found 2 Catch-All rules"):
        fix_ingress_order(input_rules)
