# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Docker Compose homelab infrastructure with automatic HTTPS via nginx-proxy and Let's Encrypt. Designed to be managed with Claude Code assistance.

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with your domain and settings

# 2. Start base infrastructure
docker compose up -d

# 3. Add a service
docker compose -f docker-compose.yml -f services/peertube.yml up -d
```

## Architecture

### Reverse Proxy Layer

All services are exposed through nginx-proxy with automatic SSL:

- **proxy** (`nginxproxy/nginx-proxy`) - Routes traffic based on VIRTUAL_HOST
- **letsencrypt-companion** (`nginxproxy/acme-companion`) - Auto-provisions SSL certificates

Services connect to `proxy-tier` network and set these environment variables:
```yaml
VIRTUAL_HOST=subdomain.${DOMAIN}
VIRTUAL_PORT=<internal-port>
LETSENCRYPT_HOST=subdomain.${DOMAIN}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}
```

## Directory Structure

```
.
├── docker-compose.yml     # Base infrastructure (proxy + letsencrypt)
├── services/              # Service definitions
│   └── peertube.yml       # Example service (PeerTube)
├── .env                   # Your configuration (gitignored)
├── .env.example           # Template configuration
├── scripts/
│   └── ovh-dns.py         # OVH DNS management (optional)
└── proxy/
    └── uploadsize.conf    # Nginx upload size config
```

## Adding a New Service

**Claude Code skill available:** Use `/add-service` for automated deployment.

### Service Template

Create `services/<name>.yml`:

```yaml
services:
  myservice:
    image: <docker-image>
    container_name: myservice
    environment:
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
      - TZ=${TZ:-Europe/Paris}
      - VIRTUAL_HOST=<subdomain>.${DOMAIN}
      - VIRTUAL_PORT=<port>
      - LETSENCRYPT_HOST=<subdomain>.${DOMAIN}
      - LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}
    volumes:
      - /data/<service>:/config
    networks:
      - proxy-tier
    restart: unless-stopped
    depends_on:
      - letsencrypt-companion

networks:
  proxy-tier:
    external: true
```

### Deployment Steps

1. **DNS** (if using OVH): `python3 scripts/ovh-dns.py add <subdomain>`
2. **Create data directory**: `sudo mkdir -p /data/<service> && sudo chown $USER:$USER /data/<service>`
3. **Start**: `docker compose -f docker-compose.yml -f services/<name>.yml up -d`
4. **Verify SSL**: `curl -sI https://<subdomain>.<domain>`

## OVH DNS Management (Optional)

Create an API token at https://eu.api.ovh.com/createToken/ with permissions:
```
GET/POST/PUT/DELETE /domain/zone/*
```

Add to `.env`:
```
OVH_APPLICATION_KEY=your_key
OVH_APPLICATION_SECRET=your_secret
OVH_CONSUMER_KEY=your_consumer_key
```

Usage:
```bash
python3 scripts/ovh-dns.py add <subdomain>      # Add CNAME record
python3 scripts/ovh-dns.py list                 # List all records
python3 scripts/ovh-dns.py check <subdomain>   # Check DNS resolution
python3 scripts/ovh-dns.py delete <subdomain>  # Delete record
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DOMAIN` | Your domain (e.g., example.com) | Yes |
| `LETSENCRYPT_EMAIL` | Email for SSL certificates | Yes |
| `PUID` / `PGID` | User/Group ID for file permissions | Yes |
| `TZ` | Timezone | Yes |
| `OVH_*` | OVH API credentials | For DNS automation |

## Troubleshooting

### SSL certificate not generated
- Check DNS resolves: `dig +short <subdomain>.<domain>`
- Check letsencrypt logs: `docker compose logs letsencrypt-companion`
- Ensure VIRTUAL_HOST and LETSENCRYPT_HOST match

### Service not accessible
- Check service is running: `docker compose ps`
- Check service logs: `docker compose logs <service>`
- Verify VIRTUAL_PORT matches the exposed port
