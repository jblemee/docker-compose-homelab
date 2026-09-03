---
name: update-services
description: Use when the user asks to update, upgrade, or check for new versions of the Docker services in this homelab.
allowed-tools: Read, Glob, Grep, Bash(docker compose:*), Bash(docker:*), Bash(curl:*), Bash(python3:*)
---

# Update Homelab Services

Pulls new images for every enabled service and recreates the containers.

## Golden rule: every command must be cwd-independent

The Bash tool keeps its working directory between calls, and parallel calls can
interleave. A relative `-f services/x.yml` will fail if another call has changed
the directory in the meantime. Prefix every command with `cd <repo root> && `,
even when a previous step already did.

## Never use `down`

`docker compose -f docker-compose.yml -f services/<x>.yml down` tears down every
service across all `-f` files, **including `proxy` and `letsencrypt-companion`**
from the base file — every site goes offline. With `-v` it also deletes the
`certs` and `acme` volumes, destroying every certificate on the server.

Updating never needs `down`: `up -d` recreates only the containers whose image
or configuration changed. To act on one service, name it explicitly
(`up -d <key>`, `stop <key>`, `rm -sf <key>`).

## Procedure

### 1. Build the compose file list

Derive it — never hardcode it, or a service added later is silently never
updated:

```bash
cd <repo root> && ls services/*.yml
```

Exclude, and report at the end as "update manually":
- files with `build:` instead of `image:` (nothing to pull — use `up -d --build <key>`)
- files whose service sets `restart: "no"` (manual-use tools)

Assemble as `-f docker-compose.yml -f services/a.yml -f services/b.yml ...` and
reuse that exact list for every command below.

### 2. Pull

```bash
cd <repo root> && docker compose $FILES pull
```

### 3. Recreate

```bash
cd <repo root> && docker compose $FILES up -d
cd <repo root> && docker compose $FILES ps
```

### 4. Verify HTTPS

Give nginx-proxy a moment to reload, then check each host:

```bash
cd <repo root> && source .env && for h in $(grep -rhoP 'VIRTUAL_HOST=\K[^\s]+' services/*.yml | sed "s/\${DOMAIN}/$DOMAIN/g" | sort -u); do
  printf '%-40s %s\n' "$h" "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "https://$h")"
done
```

**Expect a few minutes of `000` on several domains — this is not an outage.**
When many containers are recreated at once, nginx-proxy regenerates its config
and the companion re-checks certificates; during that window the TLS handshake
is refused and curl reports `000` (a client-side rejection, not an HTTP error).
Re-run the loop after a few minutes. Only investigate a host still at `000`
after the certificate count has stopped changing:

```bash
docker exec nginx-proxy ls /etc/nginx/certs/*.crt | wc -l
```

### 5. Reclaim disk

Old image layers are kept after an update:

```bash
docker image prune -f
```

Use `-a` only deliberately: it also removes images for services that are merely
stopped, forcing a full re-pull.

## Pinned tags go stale silently

`pull` only ever fetches **the tag you pinned**. If upstream abandons that tag —
project rebrand, new registry, a `:latest` that stopped moving — the pull stays
a permanent no-op, reporting success with no new layers, indistinguishable from
"already up to date". A version can sit years behind while every update run
looks clean.

Image age does not catch it either: a frozen tag still gets periodic rebuilds
(new digest, same application version). The only reliable signal is comparing
the **running application version** against the project's latest release:

```bash
docker exec <container> cat /app/package.json | grep '"version"'   # Node apps
docker inspect <container> --format '{{index .Config.Labels "org.opencontainers.image.version"}}'
```

Check this for at least the critical services whenever an update run finds
nothing new for a service that should have been moving.

## Troubleshooting

**A container stays `unhealthy` after a mass restart.** Some apps cache state at
boot and never recover if a dependency was unavailable at that instant. Restart
that one service alone rather than repeating the group restart:
`docker compose $FILES up -d --force-recreate <key>`.

**A service is missing after the update.** It is almost certainly absent from
the `-f` list. Re-derive it from `ls services/*.yml`.
