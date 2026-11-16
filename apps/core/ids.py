"""UUIDv7 на чистом Python (§2.3). Монотонность в пределах процесса."""
from __future__ import annotations

import secrets
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_seq = 0


def uuid7() -> uuid.UUID:
    global _last_ms, _seq
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms <= _last_ms:
            ms = _last_ms
            _seq = (_seq + 1) & 0xFFF
            if _seq == 0:
                ms += 1
                _last_ms = ms
        else:
            _last_ms = ms
            _seq = secrets.randbits(12)
        rand_a = _seq
    rand_b = secrets.randbits(62)
    value = (ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)
