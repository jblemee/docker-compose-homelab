# Services

Service definitions go here. Each service is a separate compose file.

## Usage

```bash
# Add a service
docker compose -f docker-compose.yml -f services/<service>.yml up -d

# View logs
docker compose -f docker-compose.yml -f services/<service>.yml logs -f

# Stop a service - ALWAYS name it (see the warning below)
docker compose -f docker-compose.yml -f services/<service>.yml stop <service-key>

# Stop and remove its containers
docker compose -f docker-compose.yml -f services/<service>.yml rm -sf <service-key>
```

### Never run a bare `down` on a multi-file command

`docker compose -f docker-compose.yml -f services/<service>.yml down` does not
stop that one service. `down` acts on **every service across all `-f` files**,
so it also removes the `proxy` and `letsencrypt-companion` defined in
`docker-compose.yml` — every site on the server goes offline at once.

With `-v` it additionally deletes the `certs` and `acme` volumes, wiping every
SSL certificate. They are then all reissued at once on the next start, which
risks hitting Let's Encrypt's duplicate-certificate rate limit.

Naming the service (`stop`, `rm -sf`, `up -d <key>`) is always safe; `down` is
not.

## Creating a Service

Use Claude Code: just describe what you want to add.

Or create `services/<name>.yml` manually - see `CLAUDE.md` for the template.

## Naming service keys

If a service needs its own database or cache, prefix the **service key** with
the service name (`myapp-postgres`, not `postgres`). Compose identifies a
container by `<project>+<service key>`, ignoring which file declared it, so a
duplicated generic key silently takes over — and recreates — another stack's
running container. See `.claude/skills/add-service/SKILL.md`.

## Required Environment Variables

Services need these env vars for the proxy:
```yaml
VIRTUAL_HOST=<subdomain>.${DOMAIN}
VIRTUAL_PORT=<internal-port>
LETSENCRYPT_HOST=<subdomain>.${DOMAIN}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}
```

And connect to `proxy-tier` network.
