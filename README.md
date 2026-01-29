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
        <img src="https://img.shields.io/github/license/AzmainMahatab/pyflared?style=flat-square" alt="License">
    </a>
  </p>
</div>

---

**Pyflared** a simple CLI tool for creating and managing Cloudflare Tunnels. No more manual token juggling or complex
configurations—just simple commands to expose your local services to the internet. You can even use it as a python
package!

## ✨ Features

- 🚀 **Quick Tunnels** — Spin up instant, temporary public URLs for local services with a single command
- 🔗 **DNS-Mapped Tunnels** — Create persistent tunnels with automatic DNS record management
- 🧹 **Automatic Cleanup** — Orphan tunnel and stale DNS record detection & removal
- 📦 **Batteries Included** — Bundles the `cloudflared` binary, no separate installation required
- 🐳 **Docker Ready** — Run as a container with minimal setup
- 🔐 **Secure by Design** — API tokens are never logged or exposed; uses Pydantic's `SecretStr`

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

### Cleanup Orphan Tunnels

Remove stale tunnels and DNS records created by pyflared:

```console
pyflared tunnel cleanup
```

## 📖 Usage

```
pyflared --help
```

### Commands

| Command                             | Description                              |
|-------------------------------------|------------------------------------------|
| `pyflared version`                  | Show the bundled cloudflared version     |
| `pyflared tunnel quick <service>`   | Create a quick tunnel to a local service |
| `pyflared tunnel mapped <pairs...>` | Create DNS-mapped tunnel(s)              |
| `pyflared tunnel cleanup`           | Remove orphan tunnels and DNS records    |

### Options for `tunnel mapped`

| Option               | Description                                                       |
|----------------------|-------------------------------------------------------------------|
| `--keep-orphans, -k` | Preserve orphan tunnels (prevents default removal)                |
| `--tunnel-name, -n`  | Specify a custom tunnel name (default: `hostname_YYYY-MM-DD_...`) |
| `--verbose, -v`      | Show detailed cloudflared logs                                    |

## 🔧 Configuration

### Environment Variables

| Variable               | Description                                     |
|------------------------|-------------------------------------------------|
| `CLOUDFLARE_API_TOKEN` | Your Cloudflare API token for tunnel management |

### API Token Permissions

For DNS-mapped tunnels, your API token needs the following permissions:

- **Account** > **Cloudflare Tunnel** > **Edit**
- **Zone** > **DNS** > **Edit**
- **Zone** > **Zone** > **Read**

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

`Pyflared` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.

## 🙏 Acknowledgments

- [cloudflared](https://github.com/cloudflare/cloudflared) — The official Cloudflare Tunnel client
- [Typer](https://typer.tiangolo.com/) — CLI framework

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/AzmainMahatab">Azmain Mahatab</a>
</p>
