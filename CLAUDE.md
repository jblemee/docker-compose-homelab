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

## Safety Rules

Two mistakes in this layout are silent, destructive, and easy to make. Read them
before running anything that stops or adds a service.

### 1. Never run a bare `down` on a multi-file command

```bash
# DESTRUCTIVE - do not run
docker compose -f docker-compose.yml -f services/<name>.yml down
```

`down` acts on **every service across all `-f` files**, not on the last one
named. It therefore removes `proxy` and `letsencrypt-companion` too, taking
every site on the server offline at once. With `-v` it also deletes the `certs`
and `acme` volumes, destroying every SSL certificate; they are then reissued in
a single burst on the next start, which can hit Let's Encrypt's
duplicate-certificate rate limit.

Always name what you want to act on — this is safe:
```bash
docker compose -f docker-compose.yml -f services/<name>.yml stop <service-key>
docker compose -f docker-compose.yml -f services/<name>.yml rm -sf <service-key>
docker compose -f docker-compose.yml -f services/<name>.yml up -d <service-key>
```

### 2. Never reuse a generic service key (`postgres`, `redis`, `db`)

With no `COMPOSE_PROJECT_NAME` set, Compose derives a single project name from
the directory for every invocation, and identifies a container by
`<project>+<service key>` — **not** by the file that declared it.

A second file declaring `postgres:` therefore points at the *same* container
slot as the first. Bringing up only the new file, without mentioning the other,
recreates (destroys and replaces) the running database with the new image and
volumes. A distinct `container_name:` does not prevent this — the collision
happens at the service-key level.

Prefix the service key with the service name: `myapp-postgres`, `myapp-redis`.
Check before writing a new file:
```bash
grep -rn "^  [a-z0-9_-]*:" services/*.yml docker-compose.yml | sort -u
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
│   ├── ovh-dns.py         # OVH DNS management (optional)
│   └── docker-user-firewall.sh  # DOCKER-USER firewall rules (optional)
├── systemd/
│   └── docker-user-firewall.service  # Applies firewall rules at boot
└── proxy/
    ├── uploadsize.conf    # client_max_body_size for large uploads
    └── ratelimit.conf     # Request/connection rate limiting
```

## Adding a New Service

**Claude Code skills available:**
- `/add-service` — adds a service end to end (DNS, compose file, SSL, verification)
- `/update-services` — pulls new images and recreates containers safely

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

1. **DNS** (if using OVH) — create **both** families, an A-only record breaks
   IPv6-only clients in a way that stays invisible for months:
   ```bash
   python3 scripts/ovh-dns.py add <subdomain> --type A
   python3 scripts/ovh-dns.py add <subdomain> --type AAAA
   python3 scripts/ovh-dns.py check <subdomain>   # warns if a family is missing
   ```
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
python3 scripts/ovh-dns.py ip                          # Show public IPv4 + IPv6
python3 scripts/ovh-dns.py add <sub> --type A          # A record (auto-detects IPv4)
python3 scripts/ovh-dns.py add <sub> --type AAAA       # AAAA record (auto-detects IPv6)
python3 scripts/ovh-dns.py add <sub>                   # CNAME (default)
python3 scripts/ovh-dns.py list                        # List all records
python3 scripts/ovh-dns.py check <sub>                 # Resolution, both families
python3 scripts/ovh-dns.py delete <sub> --type A       # Delete one record
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DOMAIN` | Your domain (e.g., example.com) | Yes |
| `LETSENCRYPT_EMAIL` | Email for SSL certificates | Yes |
| `PUID` / `PGID` | User/Group ID for file permissions | Yes |
| `TZ` | Timezone | Yes |
| `OVH_*` | OVH API credentials | For DNS automation |

## Updating Services

Use the `/update-services` skill, or manually — build the `-f` list from
`services/*.yml` rather than hardcoding it, then:

```bash
docker compose $FILES pull      # only ever fetches the tag you pinned
docker compose $FILES up -d     # recreates only what changed
docker image prune -f
```

`up -d` is the right verb; `down` is never needed to update (see Safety Rules).

## Firewall (optional but recommended)

**Docker bypasses UFW and firewalld.** It writes its own iptables rules and
evaluates them before the FORWARD chain those tools manage, so a published port
is reachable from the internet even when `ufw status` shows it denied. This is
the usual way a homelab exposes a database or admin UI it believed was closed.

`DOCKER-USER` is the chain Docker consults first and never flushes, so
container-facing rules belong there. `scripts/docker-user-firewall.sh` sets a
default-deny on the public interface, allowing only 80/443 out of the box.

```bash
# Apply now (idempotent), after reviewing ALLOWED_PORTS in the script
sudo scripts/docker-user-firewall.sh

# Install so the rules survive a reboot and Docker restarts
sudo cp scripts/docker-user-firewall.sh /usr/local/sbin/
sudo cp systemd/docker-user-firewall.service /etc/systemd/system/
sudo systemctl enable --now docker-user-firewall

# Inspect
sudo iptables -L DOCKER-USER -n -v --line-numbers
```

The rules live in memory only — without the systemd unit they are lost at the
next reboot. SSH to the host is unaffected: `DOCKER-USER` only sees traffic
forwarded to containers, host services stay governed by the INPUT chain.

To open a port, add a `"<port>/<proto>"` line to `ALLOWED_PORTS` and re-run the
script.

## Troubleshooting

### SSL certificate not generated
- Check DNS resolves: `dig +short <subdomain>.<domain>`
- Check letsencrypt logs: `docker compose logs letsencrypt-companion`
- Ensure VIRTUAL_HOST and LETSENCRYPT_HOST match

### Service not accessible
- Check service is running: `docker compose ps`
- Check service logs: `docker compose logs <service>`
- Verify VIRTUAL_PORT matches the exposed port
- If a public port is involved, check it is in `ALLOWED_PORTS` (see Firewall)

### Reachable over IPv4 but not IPv6 (or the reverse)
Check both families — `python3 scripts/ovh-dns.py check <subdomain>` warns when
one is missing. A subdomain with only an A record works for every dual-stack
client and fails only for visitors whose IPv4 path is broken, so it looks like
an isolated, intermittent outage on one service rather than a missing record.

### Many domains return `000` right after a bulk restart
Not an outage. While nginx-proxy regenerates its configuration and the companion
re-checks certificates, the TLS handshake is refused — curl reports `000`, a
client-side rejection rather than an HTTP status. It clears in a few minutes.
Watch the certificate count settle before investigating:
```bash
docker exec nginx-proxy ls /etc/nginx/certs/*.crt | wc -l
```

### A service never updates, and `pull` always reports success
`pull` only fetches the tag you pinned. If upstream abandoned it — a rebrand, a
move to another registry, a `:latest` that stopped moving — the pull becomes a
permanent no-op that is indistinguishable from "already up to date", and the
service can sit years behind. Image age does not reveal it either: a frozen tag
still gets rebuilds (new digest, same application version). Compare the running
application version to the project's latest release:
```bash
docker inspect <container> --format '{{index .Config.Labels "org.opencontainers.image.version"}}'
```
