# SPDX-FileCopyrightText: 2025-present Azmain <azmainmahatab012@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Pytest suite for Mapping.from_str - input vs expected output tests."""

import pytest
from cloudflare.types.zero_trust.tunnels.cloudflared.configuration_update_params import (
    ConfigIngress,
)

from pyflared.api_sdk.parse import Mapping


# 1. service='.../dashboard': User visits root, backend sees /dashboard. (Hide the path)
# 2. path='/dashboard': User visits /dashboard, backend sees /dashboard. (Match the path)

@pytest.mark.parametrize(
    "input_str,expected",
    [
        # Basic port only → http://localhost:port
        pytest.param(
            "app.com=8000",
            ConfigIngress(hostname="app.com", service="http://localhost:8000"),
            id="port_only",
        ),
        # Port with path
        pytest.param(
            "api.com=8000/v1/api",
            ConfigIngress(hostname="api.com", service="http://localhost:8000/v1/api"),
            id="port_with_path",
        ),
        # Full host:port
        pytest.param(
            "app.com=localhost:3000",
            ConfigIngress(hostname="app.com", service="http://localhost:3000"),
            id="host_port",
        ),
        # http_status
        pytest.param(
            "app.com=http_status:404",
            ConfigIngress(hostname="app.com", service="http_status:404"),
            id="http_status_service",
        ),
        # Known port mapping → tcp scheme
        pytest.param(
            "db.com=5432",
            ConfigIngress(hostname="db.com", service="tcp://localhost:5432"),
            id="postgres_port_tcp",
        ),
        pytest.param(
            "redis.com=6379",
            ConfigIngress(hostname="redis.com", service="tcp://localhost:6379"),
            id="redis_port_tcp",
        ),
        # SSH port → ssh scheme
        pytest.param(
            "ssh.example.com=22",
            ConfigIngress(hostname="ssh.example.com", service="ssh://localhost:22"),
            id="ssh_port",
        ),
        # HTTPS with localhost → auto no_tls_verify
        pytest.param(
            "secure.com=https://localhost:443",
            ConfigIngress(
                hostname="secure.com",
                service="https://localhost:443",
                origin_request={"no_tls_verify": True},
            ),
            id="https_localhost_no_verify",
        ),
        # HTTPS with explicit verify=false
        pytest.param(
            "api.com=https://backend:443?verify=false",
            ConfigIngress(
                hostname="api.com",
                service="https://backend:443",
                origin_request={"no_tls_verify": True},
            ),
            id="https_verify_false",
        ),
        # HTTPS with explicit verify=custom_domain
        pytest.param(
            "api.com=https://backend:443?verify=api.internal.com",
            ConfigIngress(
                hostname="api.com",
                service="https://backend:443",
                origin_request={
                    "origin_server_name": "api.internal.com",
                    "http_host_header": "api.internal.com",
                },
            ),
            id="https_verify_custom_domain",
        ),
        # Domain with path
        pytest.param(
            "app.com/api=localhost:8000",
            ConfigIngress(hostname="app.com", path="/api", service="http://localhost:8000"),
            id="domain_with_path",
        ),
        # Explicit http scheme
        pytest.param(
            "app.com=http://backend:9000",
            ConfigIngress(hostname="app.com", service="http://backend:9000"),
            id="explicit_http_scheme",
        ),
        # Unix socket
        pytest.param(
            "sock.com=/var/run/app.sock",
            ConfigIngress(hostname="sock.com", service="unix:/var/run/app.sock"),
            id="unix_socket",
        ),

    ],
)
def test_mapping_from_str(input_str: str, expected: ConfigIngress) -> None:
    """Test that Mapping.from_str produces expected ConfigIngress."""
    mapping = Mapping.from_str(input_str)
    result = mapping.service.ingress(mapping.domain)
    assert result == expected


def test_invalid_mapping_raises() -> None:
    """Missing '=' separator should raise ValueError."""
    with pytest.raises(ValueError, match=r"Invalid mapping"):
        Mapping.from_str("app.com-localhost:8000")
