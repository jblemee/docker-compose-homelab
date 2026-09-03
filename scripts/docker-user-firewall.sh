#!/bin/bash
# =============================================================================
# Docker DOCKER-USER firewall rules
# =============================================================================
# WHY THIS EXISTS
# ---------------
# Docker writes its own iptables rules and evaluates them BEFORE the FORWARD
# chain that UFW/firewalld manage. A published port (`ports: - 8080:8080`) is
# therefore reachable from the internet even when `ufw status` says the port is
# denied. This is the single most common way a homelab ends up exposing a
# database, an admin UI or a torrent client it believed was firewalled.
#
# DOCKER-USER is the one chain Docker guarantees it will consult first and never
# flush, so it is where container-facing rules belong.
#
# WHAT THIS DOES
# --------------
# Default-deny for traffic arriving on the public interface toward containers:
# only the ports listed below are allowed. Inter-container traffic, loopback and
# anything on other interfaces is untouched.
#
# USAGE
# -----
#   sudo scripts/docker-user-firewall.sh          # apply now (idempotent)
#   sudo iptables -L DOCKER-USER -n -v --line-numbers   # inspect
#
# Install as a boot-time service (rules live in memory and are lost on reboot):
#   sudo cp scripts/docker-user-firewall.sh /usr/local/sbin/
#   sudo cp systemd/docker-user-firewall.service /etc/systemd/system/
#   sudo systemctl enable --now docker-user-firewall
# =============================================================================

set -euo pipefail

# Public interface. Override with: EXT_IF=eth0 sudo -E scripts/docker-user-firewall.sh
EXT_IF="${EXT_IF:-$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')}"

if [ -z "$EXT_IF" ]; then
    echo "Error: could not detect the public interface. Set EXT_IF explicitly." >&2
    exit 1
fi

# Ports reachable from the internet. Format: "<port>/<proto>".
# 80 and 443 are required by nginx-proxy and Let's Encrypt (HTTP-01 challenge).
ALLOWED_PORTS=(
    "80/tcp"     # HTTP  - nginx-proxy + ACME challenge
    "443/tcp"    # HTTPS - nginx-proxy
    # Add a line per service that genuinely needs a direct public port, e.g.:
    # "2222/tcp"   # Git over SSH (Forgejo/Gitea)
    # "51413/tcp"  # BitTorrent
    # "51413/udp"  # BitTorrent DHT
)

# CIDRs to drop outright, before any allow rule (persistent scanners, abusive
# networks). IPv4 only - add v6 CIDRs to BLOCKED_NETS6 if needed.
BLOCKED_NETS4=()
BLOCKED_NETS6=()

# NOTE: SSH to the host itself is NOT covered by this chain. DOCKER-USER only
# sees traffic forwarded to containers; host services are governed by the INPUT
# chain (ufw, firewalld...). Locking this down does not lock you out.

apply_rules() {
    local cmd="$1" label="$2"
    local -n blocked="$3"

    # The chain only exists once Docker has set up its iptables rules for that
    # family; skip rather than abort (IPv6 is commonly disabled in Docker).
    if ! $cmd -L DOCKER-USER -n >/dev/null 2>&1; then
        echo "[$label] DOCKER-USER chain absent - skipping."
        return 0
    fi

    echo "[$label] Flushing DOCKER-USER..."
    $cmd -F DOCKER-USER

    echo "[$label] Applying rules on $EXT_IF..."

    # Established/related first: skips rule matching for the bulk of packets
    $cmd -A DOCKER-USER -i "$EXT_IF" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN

    for net in ${blocked[@]+"${blocked[@]}"}; do
        $cmd -A DOCKER-USER -i "$EXT_IF" -s "$net" -j DROP
    done

    for entry in "${ALLOWED_PORTS[@]}"; do
        $cmd -A DOCKER-USER -i "$EXT_IF" -p "${entry#*/}" --dport "${entry%/*}" -j RETURN
    done

    # Default deny for everything else arriving on the public interface
    $cmd -A DOCKER-USER -i "$EXT_IF" -j DROP

    # Anything not on the public interface (inter-container, loopback) passes
    $cmd -A DOCKER-USER -j RETURN

    echo "[$label] Done."
}

apply_rules iptables  IPv4 BLOCKED_NETS4
apply_rules ip6tables IPv6 BLOCKED_NETS6

echo "Firewall rules applied on $EXT_IF."
