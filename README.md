<p align="center">
  <h1 align="center">pyflared</h1>
  <p align="center">
    <strong>A Python CLI tool for effortless Cloudflare Tunnel management</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/pyflared"><img src="https://img.shields.io/pypi/v/pyflared.svg?style=flat-square" alt="PyPI - Version"></a>
    <a href="https://pypi.org/project/pyflared"><img src="https://img.shields.io/pypi/pyversions/pyflared.svg?style=flat-square" alt="PyPI - Python Version"></a>
    <a href="https://github.com/Azmain/pyflared/blob/main/LICENSE.txt"><img src="https://img.shields.io/github/license/Azmain/pyflared?style=flat-square" alt="License"></a>
  </p>
</p>

---

**pyflared** wraps the official `cloudflared` binary and the Cloudflare API to provide a seamless CLI experience for creating and managing Cloudflare Tunnels. No more manual token juggling or complex configurations—just simple commands to expose your local services to the internet.

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
docker pull ghcr.io/azmain/pyflared:latest
docker run --rm ghcr.io/azmain/pyflared --help
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

> **Note:** Requires a Cloudflare API token with tunnel and DNS permissions. Set via `CLOUDFLARE_API_TOKEN` environment variable or enter when prompted.

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
| ----------------------------------- | ---------------------------------------- |
| `pyflared version`                  | Show the bundled cloudflared version     |
| `pyflared tunnel quick <service>`   | Create a quick tunnel to a local service |
| `pyflared tunnel mapped <pairs...>` | Create DNS-mapped tunnel(s)              |
| `pyflared tunnel cleanup`           | Remove orphan tunnels and DNS records    |

### Options

| Option                  | Description                                    |
| ----------------------- | ---------------------------------------------- |
| `--verbose, -v`         | Show detailed cloudflared logs                 |
| `--remove-orphans, -ro` | Remove orphan tunnels before creating new ones |
| `--tunnel-name`         | Specify a custom tunnel name                   |

## 🔧 Configuration

### Environment Variables

| Variable               | Description                                     |
| ---------------------- | ----------------------------------------------- |
| `CLOUDFLARE_API_TOKEN` | Your Cloudflare API token for tunnel management |

### API Token Permissions

For DNS-mapped tunnels, your API token needs the following permissions:

- **Account** > **Cloudflare Tunnel** > **Edit**
- **Zone** > **DNS** > **Edit**
- **Zone** > **Zone** > **Read**

## 🛠️ Development

### Prerequisites

- Python 3.12+
- [Hatch](https://hatch.pypa.io/)

### Setup

```console
git clone https://github.com/Azmain/pyflared.git
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

## 🏗️ Architecture

```
pyflared/
├── cli.py           # Typer CLI application
├── _commands.py     # Core tunnel command wrappers
├── api_sdk/         # Cloudflare API integration
│   └── tunnel_manager.py  # Tunnel & DNS management
├── binary/          # cloudflared binary handling
│   ├── binary_decorator.py
│   └── process.py   # Async subprocess management
├── log/             # Logging configuration
├── shared/          # Shared types and utilities
└── utils/           # Helper utilities
```

## 📄 License

`pyflared` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.

## 🙏 Acknowledgments

- [cloudflared](https://github.com/cloudflare/cloudflared) — The official Cloudflare Tunnel client
- [Typer](https://typer.tiangolo.com/) — CLI framework
- [Cloudflare Python SDK](https://github.com/cloudflare/cloudflare-python) — Official API client

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/Azmain">Azmain</a>
</p>
