---
name: add-service
description: Add a new Docker Compose service with automatic DNS configuration (OVH) and SSL certificates. Use when adding new web services to the homelab infrastructure.
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(python3:*), Bash(docker compose:*), Bash(docker-compose:*), Bash(sudo mkdir:*), Bash(sudo chown:*), Bash(curl:*), Bash(dig:*)
---

# Add Docker Service with DNS

This skill adds a new service to the Docker Compose homelab with:
1. Automatic DNS record creation via OVH API (if configured)
2. Service YAML file creation in services/
3. SSL certificate provisioning via Let's Encrypt
4. Service startup and verification

## Prerequisites

- `.env` file with `DOMAIN` configured
- OVH API credentials in `.env` (optional, for DNS automation)
- `scripts/ovh-dns.py` script available

## Critical rule 1: never reuse a generic service key (`postgres`, `redis`, `db`)

No `COMPOSE_PROJECT_NAME` is set, so Compose derives one project name from the
directory for **every** `-f docker-compose.yml -f services/*.yml` invocation,
whichever override files are passed. Compose then identifies a container by
`<project>+<service key>` — **not** by the file that defined it.

So a new `services/<name>.yml` that declares a service key already used by
another stack takes over that stack's container. Bringing up only the new file,
without even mentioning the other one, **recreates** (destroys and replaces) the
running container with the new image, volumes and environment. A distinct
`container_name:` does not help: the collision happens at the service-key level,
before `container_name` is considered. This has taken a live database offline.

**Rule:** prefix the service key itself with the service name —
`myapp-postgres`, not `postgres` (see `services/peertube.yml` for the pattern).
Before writing the file, check the keys you plan to use:

```bash
grep -rn "^  [a-z0-9_-]*:" services/*.yml docker-compose.yml | sort -u
```

If any planned key already appears, rename it.

## Critical rule 2: always create BOTH A and AAAA records

An A-only subdomain looks perfectly healthy for months: every dual-stack client
reaches it over IPv4 and nothing complains. It breaks the day a visitor's IPv4
path degrades and their client falls back to IPv6, finding no record — which
presents as a mysterious outage on that one service while every sibling
subdomain (which does have an AAAA) keeps working. Diagnosing it from the
symptom is slow; creating both records up front costs one extra command.

## Required Information

Before adding a service, gather:
- **Service name**: e.g., `gitea`, `nextcloud`, `grafana`
- **Docker image**: e.g., `gitea/gitea`, `nextcloud:latest`
- **Subdomain**: e.g., `git` for git.${DOMAIN}
- **Internal port**: The port the container exposes (check Docker Hub)

## Step-by-Step Process

### 1. Read configuration

First, read the DOMAIN from .env:
```bash
source .env && echo "Domain: $DOMAIN"
```

### 2. Add DNS Records (if OVH configured)

Confirm what the server actually has, then create one record per family it
answers on (`add` picks the matching address automatically):

```bash
python3 scripts/ovh-dns.py ip                        # shows public IPv4 + IPv6
python3 scripts/ovh-dns.py add <subdomain> --type A
python3 scripts/ovh-dns.py add <subdomain> --type AAAA
```

Verify **both** before continuing — `check` reports each family separately and
warns when one is missing:
```bash
python3 scripts/ovh-dns.py check <subdomain>
```

Do not proceed to step 3 while a family the server supports shows `(none)`;
re-run the corresponding `add`. Allow 5-10 minutes for propagation.

### 3. Create Service File

Create `services/<service-name>.yml`:

```yaml
# =============================================================================
# <Service Name> - <Brief Description>
# =============================================================================
# Usage: docker compose -f docker-compose.yml -f services/<service-name>.yml up -d
# =============================================================================

services:
  <service-name>:
    image: <docker-image>
    container_name: <service-name>
    logging:
      options:
        max-size: "10m"
        max-file: "3"
    environment:
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
      - TZ=${TZ:-Europe/Paris}
      - VIRTUAL_HOST=<subdomain>.${DOMAIN}
      - VIRTUAL_PORT=<internal-port>
      - LETSENCRYPT_HOST=<subdomain>.${DOMAIN}
      - LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}
    volumes:
      - /data/<service-name>:/config
    networks:
      - proxy-tier
    restart: unless-stopped
    depends_on:
      - letsencrypt-companion

networks:
  proxy-tier:
    external: true
```

### 4. Create Data Directory

```bash
sudo mkdir -p /data/<service-name>
sudo chown -R $(id -u):$(id -g) /data/<service-name>
```

### 5. Start Service

```bash
docker compose -f docker-compose.yml -f services/<service-name>.yml up -d
docker compose -f docker-compose.yml -f services/<service-name>.yml logs -f <service-name>
```

### 6. Verify SSL

Wait 1-2 minutes for Let's Encrypt, then:
```bash
source .env
curl -sI https://<subdomain>.${DOMAIN} | head -5
```

### 7. Update Documentation

If the service should be documented, add it to:
- `services/README.md` - Service catalog
- `CLAUDE.md` - Main documentation (if significant)

## Common Service Configurations

### LinuxServer.io Images (Radarr, Sonarr, Lidarr, etc.)
- Port: Usually 8989 (Sonarr), 7878 (Radarr), 8686 (Lidarr)
- Volumes: `/config` for settings
- Environment: PUID, PGID, TZ

### Services needing /data access
Add volume mapping:
```yaml
volumes:
  - /data/<service-name>:/config
  - /data/media:/data/media
  - /data/downloads:/data/downloads
```

## Troubleshooting

### DNS not resolving
- Wait 5-10 minutes for propagation
- Check with: `dig +short <subdomain>.${DOMAIN}`
- Verify record exists: `python3 scripts/ovh-dns.py list`

### SSL certificate not generated
- Check letsencrypt-companion logs: `docker compose logs letsencrypt-companion`
- Ensure DNS resolves to correct IP
- Verify VIRTUAL_HOST and LETSENCRYPT_HOST match

### Service not accessible
- Check service is running: `docker compose ps`
- Check service logs: `docker compose -f docker-compose.yml -f services/<name>.yml logs <service>`
- Verify VIRTUAL_PORT matches exposed port
- Ensure service is on proxy-tier network

## Rollback

If something goes wrong:
**Never use a bare `down` here.** On a multi-file invocation it tears down every
service across all `-f` files — including the `proxy` and `letsencrypt-companion`
from `docker-compose.yml`, taking every other site offline. With `-v` it also
deletes the `certs` and `acme` volumes, destroying every SSL certificate on the
server. Always name the containers to remove:

```bash
# Stop and remove ONLY this service's containers
docker compose -f docker-compose.yml -f services/<name>.yml rm -sf <service-key> [<other-keys>...]

# Remove DNS records (if created)
python3 scripts/ovh-dns.py delete <subdomain> --type A
python3 scripts/ovh-dns.py delete <subdomain> --type AAAA

# Remove service file
rm services/<name>.yml
```
