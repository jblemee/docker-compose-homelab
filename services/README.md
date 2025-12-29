# Services

Service definitions go here. Each service is a separate compose file.

## Usage

```bash
# Add a service
docker compose -f docker-compose.yml -f services/<service>.yml up -d

# Stop a service
docker compose -f docker-compose.yml -f services/<service>.yml down

# View logs
docker compose -f docker-compose.yml -f services/<service>.yml logs -f
```

## Creating a Service

Use Claude Code: just describe what you want to add.

Or create `services/<name>.yml` manually - see `CLAUDE.md` for the template.

## Required Environment Variables

Services need these env vars for the proxy:
```yaml
VIRTUAL_HOST=<subdomain>.${DOMAIN}
VIRTUAL_PORT=<internal-port>
LETSENCRYPT_HOST=<subdomain>.${DOMAIN}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}
```

And connect to `proxy-tier` network.
