"""Нормализация клиентского IP для rate limits (Приложение E)."""

from __future__ import annotations

import ipaddress


def normalize_ip(raw: str) -> str:
    """Return the rate-limit bucket for an IP address.

    IPv6 is aggregated to its /64 so one host cannot rotate addresses inside a
    home/office prefix; IPv4-mapped IPv6 shares the plain IPv4 bucket. Invalid
    or missing values are returned unchanged and end up in a shared bucket.
    """
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return raw
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
    return str(address)
