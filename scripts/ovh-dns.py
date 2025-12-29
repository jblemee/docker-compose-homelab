#!/usr/bin/env python3
"""
OVH DNS Management Script
Manages DNS records via OVH API.

Usage:
    python3 ovh-dns.py add <subdomain> [--domain example.com]     # Adds CNAME record
    python3 ovh-dns.py add <subdomain> --type A [--ip <ip>]       # Adds A record
    python3 ovh-dns.py list [--domain example.com]
    python3 ovh-dns.py delete <subdomain> [--domain example.com]
    python3 ovh-dns.py check <subdomain> [--domain example.com]

Requires .env file with:
    DOMAIN, OVH_APPLICATION_KEY, OVH_APPLICATION_SECRET, OVH_CONSUMER_KEY
"""

import os
import sys
import hashlib
import argparse
import requests
import socket
from pathlib import Path

# Load .env file
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

OVH_ENDPOINT = "https://eu.api.ovh.com/1.0"
DEFAULT_DOMAIN = os.environ.get('DOMAIN', None)  # Read from .env, require --domain if not set


def get_server_ip():
    """Get the server's public IP address."""
    try:
        response = requests.get("https://api.ipify.org", timeout=5)
        return response.text.strip()
    except:
        try:
            response = requests.get("https://ifconfig.me", timeout=5)
            return response.text.strip()
        except:
            return None


def ovh_call(method, path, body=""):
    """Make an authenticated call to the OVH API."""
    app_key = os.environ.get('OVH_APPLICATION_KEY')
    app_secret = os.environ.get('OVH_APPLICATION_SECRET')
    consumer_key = os.environ.get('OVH_CONSUMER_KEY')

    if not all([app_key, app_secret, consumer_key]):
        print("Error: OVH API credentials not found in .env")
        print("Required: OVH_APPLICATION_KEY, OVH_APPLICATION_SECRET, OVH_CONSUMER_KEY")
        sys.exit(1)

    # Get server timestamp
    server_time = requests.get(f"{OVH_ENDPOINT}/auth/time").text

    # Calculate signature
    to_sign = f"{app_secret}+{consumer_key}+{method}+{OVH_ENDPOINT}{path}+{body}+{server_time}"
    signature = "$1$" + hashlib.sha1(to_sign.encode()).hexdigest()

    headers = {
        "X-Ovh-Application": app_key,
        "X-Ovh-Consumer": consumer_key,
        "X-Ovh-Timestamp": server_time,
        "X-Ovh-Signature": signature,
        "Content-Type": "application/json"
    }

    url = f"{OVH_ENDPOINT}{path}"

    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, headers=headers, data=body)
    elif method == "PUT":
        response = requests.put(url, headers=headers, data=body)
    elif method == "DELETE":
        response = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unknown method: {method}")

    return response


def list_records(domain, record_type=None, subdomain=None):
    """List DNS records for a domain."""
    path = f"/domain/zone/{domain}/record"
    params = []
    if record_type:
        params.append(f"fieldType={record_type}")
    if subdomain:
        params.append(f"subDomain={subdomain}")
    if params:
        path += "?" + "&".join(params)

    response = ovh_call("GET", path)
    if response.status_code != 200:
        print(f"Error listing records: {response.text}")
        return []

    record_ids = response.json()
    records = []

    for record_id in record_ids:
        r = ovh_call("GET", f"/domain/zone/{domain}/record/{record_id}")
        if r.status_code == 200:
            records.append(r.json())

    return records


def add_record(domain, subdomain, target, record_type="A", ttl=3600):
    """Add a DNS record."""
    import json

    # Check if record already exists
    existing = list_records(domain, record_type=record_type, subdomain=subdomain)
    for rec in existing:
        if rec.get('subDomain') == subdomain and rec.get('fieldType') == record_type:
            if rec.get('target') == target:
                print(f"Record already exists: {subdomain}.{domain} -> {target}")
                return True
            else:
                print(f"Record exists with different target: {rec.get('target')}")
                print(f"Updating to: {target}")
                # Delete old record
                delete_record(domain, subdomain, record_type)

    # Add new record
    body = json.dumps({
        "fieldType": record_type,
        "subDomain": subdomain,
        "target": target,
        "ttl": ttl
    })

    response = ovh_call("POST", f"/domain/zone/{domain}/record", body)

    if response.status_code in [200, 201]:
        print(f"Added {record_type} record: {subdomain}.{domain} -> {target}")
        # Refresh zone
        refresh_zone(domain)
        return True
    else:
        print(f"Error adding record: {response.text}")
        return False


def delete_record(domain, subdomain, record_type="A"):
    """Delete a DNS record."""
    records = list_records(domain, record_type=record_type, subdomain=subdomain)

    deleted = False
    for rec in records:
        if rec.get('subDomain') == subdomain:
            record_id = rec.get('id')
            response = ovh_call("DELETE", f"/domain/zone/{domain}/record/{record_id}")
            if response.status_code in [200, 204]:
                print(f"Deleted record: {subdomain}.{domain} (ID: {record_id})")
                deleted = True
            else:
                print(f"Error deleting record {record_id}: {response.text}")

    if deleted:
        refresh_zone(domain)
    elif not records:
        print(f"No {record_type} record found for {subdomain}.{domain}")

    return deleted


def refresh_zone(domain):
    """Refresh the DNS zone to apply changes."""
    response = ovh_call("POST", f"/domain/zone/{domain}/refresh")
    if response.status_code in [200, 204]:
        print(f"Zone {domain} refreshed")
        return True
    else:
        print(f"Warning: Could not refresh zone: {response.text}")
        return False


def check_record(domain, subdomain):
    """Check if a subdomain resolves correctly."""
    fqdn = f"{subdomain}.{domain}"

    # Check DNS
    try:
        ip = socket.gethostbyname(fqdn)
        print(f"DNS resolution: {fqdn} -> {ip}")
        return ip
    except socket.gaierror:
        print(f"DNS resolution failed for {fqdn}")
        return None


def main():
    parser = argparse.ArgumentParser(description="OVH DNS Management")
    parser.add_argument("action", choices=["add", "list", "delete", "check", "ip"],
                       help="Action to perform")
    parser.add_argument("subdomain", nargs="?", help="Subdomain to manage")
    domain_help = f"Domain (default: {DEFAULT_DOMAIN})" if DEFAULT_DOMAIN else "Domain (required, or set DOMAIN in .env)"
    parser.add_argument("--domain", "-d", default=DEFAULT_DOMAIN, help=domain_help)
    parser.add_argument("--ip", "--target", help="Target: IP for A records, domain for CNAME")
    parser.add_argument("--type", "-t", default="CNAME", help="Record type (default: CNAME)")
    parser.add_argument("--ttl", type=int, default=3600, help="TTL in seconds (default: 3600)")

    args = parser.parse_args()

    if args.action == "ip":
        ip = get_server_ip()
        if ip:
            print(f"Server public IP: {ip}")
        else:
            print("Could not determine server IP")
        return

    # Validate domain is set for actions that need it
    if args.action != "ip" and not args.domain:
        parser.error("--domain is required (or set DOMAIN in .env)")

    if args.action == "list":
        records = list_records(args.domain, subdomain=args.subdomain)
        if not records:
            print(f"No records found for {args.domain}")
            return

        print(f"\nDNS Records for {args.domain}:")
        print("-" * 60)
        for rec in sorted(records, key=lambda x: (x.get('subDomain', ''), x.get('fieldType', ''))):
            sub = rec.get('subDomain') or '@'
            print(f"  {sub:20} {rec.get('fieldType'):6} {rec.get('target')}")
        return

    if not args.subdomain:
        parser.error(f"subdomain is required for {args.action}")

    if args.action == "add":
        if args.type == "CNAME":
            # CNAME default target is the domain itself (e.g., example.com.)
            target = args.ip or f"{args.domain}."
        else:
            # A record needs an IP
            target = args.ip or get_server_ip()
            if not target:
                print("Error: Could not determine IP address. Use --ip/--target to specify.")
                sys.exit(1)
        add_record(args.domain, args.subdomain, target, args.type, args.ttl)

    elif args.action == "delete":
        delete_record(args.domain, args.subdomain, args.type)

    elif args.action == "check":
        check_record(args.domain, args.subdomain)


if __name__ == "__main__":
    main()
