<div align="center">
  <h1>Pyflared</h1>
  <p>
    <strong>A Python CLI tool for effortless Cloudflare Tunnel management</strong>
  </p>
  <p>
    <a href="https://pypi.org/project/pyflared"><img src="https://img.shields.io/pypi/v/pyflared.svg?style=flat-square" alt="PyPI - Version"></a>
    <a href="https://pypi.org/project/pyflared"><img src="https://img.shields.io/pypi/pyversions/pyflared.svg?style=flat-square" alt="PyPI - Python Version"></a>
    <a href="https://pepy.tech/project/pyflared">
        <img src="https://static.pepy.tech/badge/pyflared" alt="Pepy Downloads">
    </a>    
    <a href="https://github.com/cloudflare/cloudflared/releases/latest">
        <img src="https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2FAzmainMahatab%2Fpyflared%2Fmain%2Fcloudflared.version&query=%24&label=cloudflared" alt="Cloudflared Version">
    </a>
    <a href="https://github.com/AzmainMahatab/pyflared/blob/main/LICENSE.txt">
        <img src="https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square" alt="License">
    </a>
  </p>
</div>

---

**Pyflared** is a CLI tool for creating and managing Cloudflare Tunnels. No more manual token juggling or complex
configurations — just simple commands to expose your local services to the internet. It also works as a Python library!

## ✨ Features

- 🚀 **Quick Tunnels** — Spin up instant, temporary public URLs for local services with a single command
- 🔗 **DNS-Mapped Tunnels** — Create persistent tunnels with automatic DNS record management
- 🧹 **Automatic Cleanup** — Orphan tunnel and stale DNS record detection & removal
- 🔑 **SSH over Cloudflare** — Expose and connect to SSH servers through Cloudflare Tunnels
- 🗝️ **Token Management** — Store and manage multiple Cloudflare API tokens locally
- 📦 **Batteries Included** — Bundles the `cloudflared` binary, no separate installation required
- 🐳 **Docker Ready** — Run as a container with minimal setup

## 📦 Installation

### Using `uv` (Recommended)

```console
uv tool install pyflared
```

### Using `pip`

```console
pip install pyflared
```

### Using Docker

```console
docker pull ghcr.io/azmainmahatab/pyflared:latest
docker run --rm ghcr.io/azmainmahatab/pyflared --help
```

## 🚀 Quick Start

### Create a Quick Tunnel

Expose a local service instantly with a temporary `trycloudflare.com` URL:

```console
pyflared tunnel quick 8000
```

This creates a public URL (e.g., `https://random-name.trycloudflare.com`) pointing to `localhost:8000`.

### Create a DNS-Mapped Tunnel

Create a persistent tunnel with your own domain:

```console
pyflared tunnel mapped api.example.com=localhost:8000 web.example.com=localhost:3000
```

This will:

1. Create a new Cloudflare Tunnel
2. Configure DNS records for your domains
3. Route traffic to your local services

> **Note:** Requires a Cloudflare API token with tunnel and DNS permissions. Set via `CLOUDFLARE_API_TOKEN` environment
> variable or enter when prompted.

### Clean Up Orphan Tunnels

Remove stale tunnels and DNS records left behind by pyflared:

```console
pyflared tunnel cleanup
```

### Expose SSH via Cloudflare

Serve your local SSH daemon through a Cloudflare Tunnel:

```console
pyflared ssh serve ssh.example.com
```

Connect to it from another machine:

```console
pyflared ssh connect user@ssh.example.com
```

## 📖 Usage

```console
pyflared --help
```

### `pyflared version`

Show the bundled cloudflared version.

### `pyflared tunnel quick <service>`

Create a quick tunnel to a local service with a temporary `trycloudflare.com` URL.

| Option         | Description                    |
|----------------|--------------------------------|
| `--verbose -v` | Show detailed cloudflared logs |

### `pyflared tunnel mapped <DOMAIN=SERVICE..>`

Create DNS-mapped tunnel(s). See [Mapping Format](#-mapping-format) for all supported `DOMAIN=SERVICE` syntaxes.

| Option             | Description                                                                                          |
|--------------------|------------------------------------------------------------------------------------------------------|
| `--tunnel-name -n` | Custom tunnel name (default: auto-generated). See [Tunnel Naming Behavior](#-tunnel-naming-behavior) |
| `--force -f`       | Take over DNS from other tunnels even if named                                                       |
| `--verbose -v`     | Show detailed cloudflared logs                                                                       |

### `pyflared tunnel cleanup`

Remove orphan tunnels and DNS records.

| Option         | Description                                            |
|----------------|--------------------------------------------------------|
| `--all -a`     | Delete ALL tunnels and DNS records, not just orphans   |
| `--force -f`   | Bypass confirmation prompt when deleting all resources |
| `--verbose -v` | Show detailed cloudflared logs                         |

### `pyflared ssh serve <domain>`

Expose local SSH server through a Cloudflare Tunnel.

| Option             | Description                                                                |
|--------------------|----------------------------------------------------------------------------|
| `--tunnel-name -n` | Custom tunnel name. See [Tunnel Naming Behavior](#-tunnel-naming-behavior) |
| `--force -f`       | Take over DNS from other tunnels even if named                             |
| `--verbose -v`     | Show detailed cloudflared logs                                             |

### `pyflared ssh add <hostname>`

Add a Cloudflare SSH host entry to your `~/.ssh/config`.

### `pyflared ssh remove <alias>`

Remove a previously added SSH config entry.

### `pyflared ssh connect <user@host> [args]`

Connect to a remote host using SSH through Cloudflare. Extra SSH arguments are passed through.

### `pyflared ssh proxy <hostname>`

ProxyCommand helper for use in `~/.ssh/config`:

```
Host myhost
    ProxyCommand pyflared ssh proxy %h
```

### `pyflared token list`

List all stored Cloudflare API tokens.

### `pyflared token add <name>`

Add a new API token (prompts securely for the token value).

### `pyflared token remove <name>`

Remove a stored token by its friendly name.

### `pyflared token nuke`

Remove all stored tokens.

## 🏷️ Tunnel Naming Behavior

The `--tunnel-name / -n` flag on `tunnel mapped` and `ssh serve` controls the tunnel lifecycle:

|                    | Without `--tunnel-name` (default)                                                 | With `--tunnel-name`                                                              |
|--------------------|-----------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| **Lifecycle**      | Ephemeral — tunnel and DNS records are automatically deleted on shutdown (Ctrl+C) | Persistent — tunnel and DNS records are preserved across runs                     |
| **Next run**       | A brand-new tunnel is created every time                                          | Reuses the existing tunnel if the same name exists                                |
| **DNS protection** | None — DNS records are disposable                                                 | Named tunnels protect their DNS records from being claimed by other tunnel setups |
| **Force override** | N/A                                                                               | Use `--force / -f` to override DNS owned by another named tunnel                  |

> **Tip:** Use unnamed tunnels for development and quick testing. Use named tunnels for long-lived services where you
> want DNS stability and protection across restarts.

## 📐 Mapping Format

The `DOMAIN=SERVICE` pairs used in `tunnel mapped` support a variety of formats.

### Basic

```console
# Port only → inferred as http://localhost:<port>
pyflared tunnel mapped app.com=8000

# Host and port
pyflared tunnel mapped app.com=localhost:3000

# Explicit scheme
pyflared tunnel mapped app.com=http://backend:9000
pyflared tunnel mapped secure.com=https://localhost:443
```

### Path Routing

```console
# Route a subdomain path to a specific backend path
pyflared tunnel mapped app.com/api=localhost:8000

# Port with backend path
pyflared tunnel mapped api.com=8000/v1/api
```

### TCP & SSH

Well-known ports are automatically mapped to the correct protocol:

```console
# SSH (port 22) → ssh://
pyflared tunnel mapped ssh.example.com=22

# PostgreSQL (5432), Redis (6379), MongoDB (27017) → tcp://
pyflared tunnel mapped db.com=5432
pyflared tunnel mapped redis.com=6379
```

### Unix Sockets

```console
pyflared tunnel mapped sock.com=/var/run/app.sock
```

### TLS Verification

| Syntax                                            | Behavior                                       |
|---------------------------------------------------|------------------------------------------------|
| `https://localhost:443`                           | Auto-disables TLS verification (local backend) |
| `https://backend:443?verify_tls=false`            | Explicitly disable TLS verification            |
| `https://localhost?verify_tls=true`               | Force TLS verification even for localhost      |
| `https://backend:443?verify_tls=api.internal.com` | Verify against a custom server name            |

### Special Services

```console
# Cloudflare built-in test page
pyflared tunnel mapped test.com=hello_world

# HTTP status code response
pyflared tunnel mapped app.com=http_status:404

# Bastion mode (SSH browser rendering)
pyflared tunnel mapped bastion.com=bastion
```

## 🔧 Configuration

### Environment Variables

| Variable               | Description                                     |
|------------------------|-------------------------------------------------|
| `CLOUDFLARE_API_TOKEN` | Your Cloudflare API token for tunnel management |

### API Token Permissions

For DNS-mapped tunnels, your API token needs the following permissions:

- **Account** > **Cloudflare Tunnel** > **Edit**
- **Zone** > **DNS** > **Edit**

## ❓ Troubleshooting

### SSL Handshake Failed (Error 525)

If you see an **Error 525** page ("SSL handshake failed") immediately after creating a tunnel, don't worry—this is a
temporary issue. Cloudflare's edge network may take a few moments to fully propagate the tunnel configuration.

**What to do:** Simply wait 1-2 minutes and refresh the page. The error will resolve automatically once the tunnel is
fully established.

## 🛠️ Development

### Prerequisites

- Python 3.12+
- [Hatch](https://hatch.pypa.io/)

### Setup

```console
git clone https://github.com/AzmainMahatab/pyflared.git
cd pyflared
hatch env create
```

### Running Tests

```console
hatch test
```

### Type Checking

```console
hatch run types:check
```

### Building

```console
hatch build
```

## 📄 License

`Pyflared` is distributed under the terms of the [MPL-2.0](https://www.mozilla.org/en-US/MPL/2.0/) license.

## 🙏 Acknowledgments

- [cloudflared](https://github.com/cloudflare/cloudflared) — The official Cloudflare Tunnel client
- [Typer](https://typer.tiangolo.com/) — CLI framework

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/AzmainMahatab">Azmain Mahatab</a>
</p>
