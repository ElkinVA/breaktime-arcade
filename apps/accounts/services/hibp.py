"""Проверка пароля по HIBP k-anonymity (§2.10.2)."""

from __future__ import annotations

import hashlib
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class HIBPUnavailable(RuntimeError):
    """Проверка утечек недоступна; регистрация должна fail closed."""


def password_is_pwned(password: str) -> bool:
    if not getattr(settings, "HIBP_ENABLED", False):
        return False

    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # noqa: S324
    prefix, suffix = digest[:5], digest[5:]
    request = Request(
        f"https://api.pwnedpasswords.com/range/{prefix}",
        headers={"User-Agent": "BreaktimeArcade/registration"},
    )
    try:
        with urlopen(request, timeout=settings.HIBP_TIMEOUT_SECONDS) as response:  # noqa: S310
            body = response.read().decode("ascii", "ignore")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("account.hibp.unavailable", exc_info=exc)
        raise HIBPUnavailable("password breach check unavailable") from exc

    for line in body.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.upper() == suffix:
            try:
                return int(count) > 0
            except ValueError:
                return True
    return False
