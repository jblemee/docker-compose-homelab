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

# Load .env file.
# The .env lives at the repository root while this script sits in scripts/, so
# looking only next to the script silently finds nothing and every OVH call
# then fails on missing credentials. Check the repo root and the cwd too.
for env_candidate in [
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent / ".env",
    Path.cwd() / ".env",
]:
    if env_candidate.exists():
        with open(env_candidate) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())
        break

OVH_ENDPOINT = "https://eu.api.ovh.com/1.0"
DEFAULT_DOMAIN = os.environ.get('DOMAIN', None)  # Read from .env, require --domain if not set


def get_server_ip(family="ipv4"):
    """Get the server's public IP address for the given family ("ipv4"/"ipv6").

    The family matters: a generic lookup returns whichever protocol the request
    happened to use, so asking for an AAAA target and getting an IPv4 back
    would publish a broken record.
    """
    endpoints = {
        "ipv4": ["https://api4.ipify.org", "https://ipv4.icanhazip.com"],
        "ipv6": ["https://api6.ipify.org", "https://ipv6.icanhazip.com"],
    }[family]
    for url in endpoints:
        try:
            response = requests.get(url, timeout=5)
            if response.ok and response.text.strip():
                return response.text.strip()
        except requests.RequestException:
            continue
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
    """Check that a subdomain resolves over BOTH IPv4 and IPv6.

    Checking only IPv4 (socket.gethostbyname) is how a missing AAAA record
    stays invisible for months: everything works from any dual-stack client,
    right up until a visitor whose IPv4 path is broken falls back to IPv6 and
    finds nothing there. Report each family separately so the gap is obvious.
    """
    # An empty subdomain means the apex record; f"{''}.{domain}" would query
    # ".example.com" and always fail to resolve.
    fqdn = f"{subdomain}.{domain}" if subdomain else domain

    results = {}
    for label, family in (("A", socket.AF_INET), ("AAAA", socket.AF_INET6)):
        try:
            infos = socket.getaddrinfo(fqdn, None, family)
            addrs = sorted({info[4][0] for info in infos})
        except socket.gaierror:
            addrs = []
        results[label] = addrs
        if addrs:
            print(f"  {label:4} {fqdn} -> {', '.join(addrs)}")
        else:
            print(f"  {label:4} {fqdn} -> (none)")

    if not any(results.values()):
        print(f"DNS resolution failed for {fqdn}")
    elif not all(results.values()):
        missing = [k for k, v in results.items() if not v]
        print(f"WARNING: {fqdn} has no {'/'.join(missing)} record - "
              f"it will be unreachable for clients using that protocol.")
    return results


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
        v4 = get_server_ip("ipv4")
        v6 = get_server_ip("ipv6")
        print(f"Server public IPv4: {v4 or '(none)'}")
        print(f"Server public IPv6: {v6 or '(none)'}")
        if not v4 and not v6:
            sys.exit(1)
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
            # A/AAAA records need an IP of the matching family
            family = "ipv6" if args.type.upper() == "AAAA" else "ipv4"
            target = args.ip or get_server_ip(family)
            if not target:
                print(f"Error: Could not determine {family} address. "
                      f"Use --ip/--target to specify.")
                sys.exit(1)
        add_record(args.domain, args.subdomain, target, args.type, args.ttl)

    elif args.action == "delete":
        delete_record(args.domain, args.subdomain, args.type)

    elif args.action == "check":
        check_record(args.domain, args.subdomain)


if __name__ == "__main__":
    main()
