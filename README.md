# Docker Compose Homelab

Self-hosted services with automatic HTTPS, designed to be managed with [Claude Code](https://claude.ai/code).

## Features

- **Automatic HTTPS** via nginx-proxy + Let's Encrypt
- **Modular services** - add any Docker service easily
- **Claude Code integration** - AI-assisted service management
- **OVH DNS automation** - automatic DNS record creation (optional)

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/jblemee/docker-compose-homelab.git
cd docker-compose-homelab

cp .env.example .env
nano .env  # Set your domain and credentials
```

### 2. Start infrastructure

```bash
# Start reverse proxy
docker compose up -d
```

### 3. Add services

With Claude Code, simply ask:
- *"Add PeerTube to my homelab"*
- *"Create a Jellyfin service"*
- *"Set up Nextcloud"*

Or manually:
```bash
docker compose -f docker-compose.yml -f services/peertube.yml up -d
```

## Usage with Claude Code

This project includes a skill that helps Claude Code:
1. Create service configuration files
2. Set up DNS records (via OVH API)
3. Deploy and verify services

Just describe what you want and Claude Code handles the rest.

## DNS Setup

### Option 1: Manual DNS

Add CNAME records pointing to your server for each service subdomain.

### Option 2: OVH API (automated)

1. Create API token at https://eu.api.ovh.com/createToken/
2. Add credentials to `.env`
3. Let Claude Code manage DNS automatically

## Requirements

- Docker & Docker Compose v2
- A domain name with DNS access
- Port 80 and 443 available
- Python 3 (for OVH DNS script, optional)

## Configuration

All configuration via `.env`. Required variables:

| Variable | Description |
|----------|-------------|
| `DOMAIN` | Your domain (e.g., example.com) |
| `LETSENCRYPT_EMAIL` | Email for SSL certificates |
| `PUID` / `PGID` | User/Group ID (run `id` to find) |
| `TZ` | Timezone (e.g., Europe/Paris) |

## License

[WTFPL](LICENSE) - Do What The Fuck You Want To Public License.
