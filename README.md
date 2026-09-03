# Docker Compose Homelab

Self-hosted services with automatic HTTPS, designed to be managed with [Claude Code](https://claude.ai/code).

## Features

- **Automatic HTTPS** via nginx-proxy + Let's Encrypt
- **Modular services** - add any Docker service easily
- **Claude Code integration** - AI-assisted service management
- **OVH DNS automation** - dual-stack A + AAAA records (optional)
- **Hardening** - nginx rate limiting and a default-deny `DOCKER-USER` firewall

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

### 4. Lock down container ports (recommended)

Docker bypasses UFW and firewalld, so a published port is reachable from the
internet even when `ufw status` says otherwise. Review `ALLOWED_PORTS` in
`scripts/docker-user-firewall.sh` (80 and 443 by default), then:

```bash
sudo scripts/docker-user-firewall.sh
sudo cp scripts/docker-user-firewall.sh /usr/local/sbin/
sudo cp systemd/docker-user-firewall.service /etc/systemd/system/
sudo systemctl enable --now docker-user-firewall
```

## Stopping a service

```bash
docker compose -f docker-compose.yml -f services/<name>.yml stop <service-key>
```

> **Never run a bare `down` on a multi-file command.** It acts on every service
> across all `-f` files, so it also removes the proxy and the Let's Encrypt
> companion — every site goes offline. With `-v` it deletes the certificate
> volumes too. Always name the service you mean.

## Usage with Claude Code

This project includes two skills:

- **`add-service`** - creates the service file, DNS records and data directory,
  deploys, and verifies SSL. It also encodes two failure modes that are easy to
  hit and hard to diagnose: Compose service-key collisions that silently
  recreate another stack's database, and A-only DNS records.
- **`update-services`** - pulls new images and recreates containers safely.

Just describe what you want and Claude Code handles the rest.

## DNS Setup

Create **both** an A and an AAAA record for every subdomain. An A-only record
works from any dual-stack client and fails only for visitors whose IPv4 path is
broken, which surfaces much later as a mysterious per-service outage.

### Option 1: Manual DNS

Add records pointing to your server for each service subdomain.

### Option 2: OVH API (automated)

1. Create API token at https://eu.api.ovh.com/createToken/
2. Add credentials to `.env`
3. Let Claude Code manage DNS automatically, or:

```bash
python3 scripts/ovh-dns.py ip                     # show public IPv4 + IPv6
python3 scripts/ovh-dns.py add <sub> --type A
python3 scripts/ovh-dns.py add <sub> --type AAAA
python3 scripts/ovh-dns.py check <sub>            # warns if a family is missing
```

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
