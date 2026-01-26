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
        # HTTPS with explicit verify_tls=false
        pytest.param(
            "api.com=https://backend:443?verify_tls=false",
            ConfigIngress(
                hostname="api.com",
                service="https://backend:443",
                origin_request={"no_tls_verify": True},
            ),
            id="https_verify_false",
        ),
        # HTTPS with explicit verify_tls=custom_domain
        pytest.param(
            "api.com=https://backend:443?verify_tls=api.internal.com",
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

        # --- Missing TCP/Socket Cases ---
        # Remote host with known TCP port (e.g., Mongo)
        pytest.param(
            "mongo.internal=my-db:27017",
            ConfigIngress(hostname="mongo.internal", service="tcp://my-db:27017"),
            id="remote_tcp_port",
        ),

        # Unix + TLS
        pytest.param(
            "secure-sock.local=unix+tls:///var/run/secure.sock",
            ConfigIngress(
                hostname="secure-sock.local",
                service="unix+tls:/var/run/secure.sock",  # Single slash is correct!
                origin_request={"no_tls_verify": True}  # Assuming local sockets default to no verify like localhost
            ),
            id="unix_tls_socket",
        ),

        # --- Special Cloudflare Services ---
        # hello_world service
        pytest.param(
            "test.com=hello_world",
            ConfigIngress(hostname="test.com", service="hello_world"),
            id="hello_world_service",
        ),
        # hello-world service (alternate spelling)
        pytest.param(
            "test2.com=hello-world",
            ConfigIngress(hostname="test2.com", service="hello-world"),
            id="hello_world_alt_service",
        ),
        # bastion service
        pytest.param(
            "bastion.com=bastion",
            ConfigIngress(hostname="bastion.com", service="bastion"),
            id="bastion_service",
        ),
        # socks5 service
        pytest.param(
            "proxy.com=socks5",
            ConfigIngress(hostname="proxy.com", service="socks5"),
            id="socks5_service",
        ),

        # --- Missing Verification Logic Cases ---
        # HTTPS Remote Default (Should stay secure)
        pytest.param(
            "google.com=https://google.com",
            ConfigIngress(hostname="google.com", service="https://google.com"),
            id="https_remote_default_secure",
        ),
        # HTTPS IP Localhost (127.0.0.1) -> Auto Insecure
        pytest.param(
            "local-ip.com=https://127.0.0.1:443",
            ConfigIngress(
                hostname="local-ip.com",
                service="https://127.0.0.1:443",
                origin_request={"no_tls_verify": True},
            ),
            id="https_127_0_0_1_auto_insecure",
        ),
        # HTTPS Localhost Forced Secure (verify_tls=true)
        pytest.param(
            "forced.com=https://localhost?verify_tls=true",
            ConfigIngress(hostname="forced.com", service="https://localhost"),
            id="https_localhost_forced_secure",
        ),
        # HTTP with verify_tls param (Should be ignored)
        pytest.param(
            "plain.com=http://localhost:8080?verify_tls=false",
            ConfigIngress(hostname="plain.com", service="http://localhost:8080"),
            id="http_ignores_verify_param",
        ),
    ],
)
def test_mapping_from_str(input_str: str, expected: ConfigIngress) -> None:
    """Test that Mapping.from_str produces expected ConfigIngress."""
    mapping = Mapping.from_str(input_str)
    result = mapping.ingress()
    assert result == expected


def test_invalid_mapping_raises() -> None:
    """Missing '=' separator should raise ValueError."""
    with pytest.raises(ValueError, match=r"Invalid mapping"):
        Mapping.from_str("app.com-localhost:8000")
