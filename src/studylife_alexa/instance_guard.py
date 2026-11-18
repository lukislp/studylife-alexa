"""Outbound-request policy for the user-supplied StudyAtrium instance URL (audit
2026-11-16 L23).

`/authorize` is public and, before redirecting a browser anywhere, makes this server
GET `<instance_url>/api/system/version`. Left unchecked, anyone could point that
request at internal addresses (cluster services, cloud metadata, loopback) - a blind
SSRF. This module holds the policy, separate from the OAuth flow:

* the URL must be a plain https URL (no credentials, query or fragment);
* optionally, its host must be on an operator allow-list (ALEXA_ALLOWED_INSTANCE_HOSTS);
* every address the host resolves to must be globally routable - no loopback,
  private, link-local, carrier-grade NAT, multicast or reserved ranges.

Self-hosters keep working with no configuration: any public https host passes unless
the operator opts in to an allow-list.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 4096
REQUEST_TIMEOUT_SECONDS = 5.0


def parse_allowed_hosts(raw: str | None) -> frozenset[str]:
    return frozenset(host.strip().lower() for host in (raw or "").split(",") if host.strip())


def is_acceptable_instance_url(url: str) -> bool:
    """Syntax-only check (no network): https, a hostname, no userinfo/query/fragment."""
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and bool(hostname)
        and "@" not in parts.netloc
        and not parts.query
        and not parts.fragment
    )


def is_host_allowed(url: str, allowed_hosts: frozenset[str]) -> bool:
    """True when no allow-list is configured, else when the URL's host is on it."""
    if not allowed_hosts:
        return True
    hostname = urlsplit(url).hostname
    return hostname is not None and hostname.lower() in allowed_hosts


async def resolves_to_public_addresses_only(url: str) -> bool:
    """Resolves the URL's host and requires EVERY returned address to be globally
    routable (one private answer among public ones is still a rebinding foothold).

    Residual risk, accepted: the HTTP client resolves the name again when it connects,
    so a DNS-rebinding host could answer differently the second time. The response is
    never shown to the caller (only "is this a StudyAtrium instance" comes back), so the
    exposure is a blind request, not a data leak."""
    parts = urlsplit(url)
    hostname = parts.hostname
    if hostname is None:
        return False
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            hostname, parts.port or 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]  # strip an IPv6 zone id
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        # An IPv4-mapped IPv6 address inherits the policy of the IPv4 it wraps.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            return False
    return True
