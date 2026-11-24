"""Real-Redis atomicity for account rate limits.

The rest of the account suite uses LocMem; this test deliberately uses the
configured ``throttle`` alias so a pickled/fallback counter cannot hide a
lost-update bug. It needs the redis-throttle service (present in dev/CI).
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

from django.core.cache import caches

from apps.accounts.services import rate_limit


def _device_key(device: str) -> str:
    return f"auth:register:device:{rate_limit._hash(device)}"


def _ip_key(ip: str) -> str:
    return f"auth:register:ip:{rate_limit._ip_hash(ip)}"


def test_throttle_cache_uses_json_for_integer_counters() -> None:
    from django.conf import settings

    options = settings.CACHES["throttle"]["OPTIONS"]
    assert options["SERIALIZER"] == "django_redis.serializers.json.JSONSerializer"


def test_registration_ip_cap_is_atomic_on_real_redis() -> None:
    suffix = uuid.uuid4().hex
    seed_devices = [f"seed-{suffix}-{index}" for index in range(29)]
    devices = [f"race-{suffix}-{index}" for index in range(20)]
    ip = "198.18.7.7"
    keys = [
        _ip_key(ip),
        *(_device_key(item) for item in seed_devices),
        *(_device_key(item) for item in devices),
    ]
    for key in keys:
        caches["throttle"].delete(key)
    try:
        for device in seed_devices:
            assert rate_limit.registration_attempt(device, ip).allowed
        with ThreadPoolExecutor(max_workers=20) as pool:
            decisions = list(
                pool.map(
                    lambda device: rate_limit.registration_attempt(device, ip),
                    devices,
                )
            )
        assert sum(decision.allowed for decision in decisions) == 1
    finally:
        for key in keys:
            caches["throttle"].delete(key)
