"""Remove runtime bundles that no GameVersion references (§5.5)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
from pathlib import Path

from django.conf import settings

from apps.catalog.models import GameVersion

logger = logging.getLogger("apps.pipeline.runtime_cleanup")

RUNTIME_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _remove_bundle(entry: os.DirEntry[str]) -> bool:
    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
        return False
    try:
        shutil.rmtree(entry.path)
    except OSError:
        return False
    return not Path(entry.path).exists()


def cleanup_orphan_runtimes(
    *,
    runtime_root: Path | None = None,
    ttl_seconds: int | None = None,
    now: float | None = None,
) -> dict[str, int]:
    """Delete unreferenced runtime bundles older than the TTL; idempotent."""
    root = Path(runtime_root or settings.ZIP_PUBLIC_RUNTIME_ROOT)
    if root.is_symlink() or not root.is_dir():
        return {"removed": 0, "skipped": 0}
    ttl = settings.ZIP_RUNTIME_ORPHAN_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    cutoff = (time.time() if now is None else now) - ttl
    referenced = set(GameVersion.objects.values_list("runtime_hash", flat=True))
    removed = 0
    skipped = 0
    try:
        hosts = list(os.scandir(root))
    except OSError:
        return {"removed": 0, "skipped": 0}
    for host in hosts:
        if host.is_symlink() or not host.is_dir(follow_symlinks=False):
            continue
        if RUNTIME_HASH_RE.fullmatch(host.name):
            bundles = [(host, host.name)]
        else:
            try:
                bundles = [
                    (entry, entry.name)
                    for entry in os.scandir(host.path)
                    if entry.is_dir(follow_symlinks=False) and RUNTIME_HASH_RE.fullmatch(entry.name)
                ]
            except OSError:
                continue
        for entry, runtime_hash in bundles:
            if runtime_hash in referenced:
                skipped += 1
                continue
            try:
                if entry.is_symlink() or entry.stat(follow_symlinks=False).st_mtime >= cutoff:
                    skipped += 1
                    continue
            except OSError:
                skipped += 1
                continue
            if _remove_bundle(entry):
                removed += 1
                logger.info(
                    "pipeline.runtime_orphan_removed",
                    extra={"runtime_hash": runtime_hash, "path": entry.path},
                )
            else:
                skipped += 1
    return {"removed": removed, "skipped": skipped}
