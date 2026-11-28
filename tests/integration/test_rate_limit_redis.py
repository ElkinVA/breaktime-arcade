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


def test_registration_release_is_floor_safe_and_atomic_on_real_redis() -> None:
    suffix = uuid.uuid4().hex
    device = f"release-{suffix}"
    ip = "198.18.7.8"
    cache = caches["throttle"]
    device_key = _device_key(device)
    ip_key = _ip_key(ip)
    for key in (device_key, ip_key):
        cache.delete(key)
    try:
        # Two reservations -> a single release must leave exactly one slot.
        assert rate_limit.registration_attempt(device, ip).allowed
        assert rate_limit.registration_attempt(device, ip).allowed
        assert int(cache.get(device_key)) == 2
        assert int(cache.get(ip_key)) == 2
        rate_limit.release_registration(device, ip)
        assert int(cache.get(device_key)) == 1
        assert int(cache.get(ip_key)) == 1

        # Simultaneous releases beyond the reservation count must clamp at 0.
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(lambda _: rate_limit.release_registration(device, ip), range(16)))
        assert int(cache.get(device_key)) == 0
        assert int(cache.get(ip_key)) == 0

        # A late release on an empty counter must not undercount it.
        rate_limit.release_registration(device, ip)
        assert int(cache.get(device_key)) == 0
        assert int(cache.get(ip_key)) == 0
    finally:
        for key in (device_key, ip_key):
            cache.delete(key)
