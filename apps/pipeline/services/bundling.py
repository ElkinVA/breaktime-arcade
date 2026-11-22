"""Runtime bundle construction (§2.14.3).

The bundle is a byte-for-byte copy of the package tree with exactly one file
changed — the official SDK. ``package_hash`` (original ZIP) and
``runtime_hash`` (bundle tree) are tracked independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from apps.pipeline.services.artifacts import copy_tree, runtime_hash_for, tree_hashes
from apps.pipeline.services.critical_path import CriticalPathResult, measure_critical_path
from apps.pipeline.services.injection import InjectionReport, inject_sdk


@dataclass(slots=True)
class BundleResult:
    staging: Path
    files: dict[str, str]
    runtime_hash: str
    injection_report: InjectionReport
    critical_path: CriticalPathResult


def build_runtime(
    source_root: Path,
    staging: Path,
    *,
    sdk_path: Path,
    sdk_version: str,
    sdk_contract_version: str,
    critical: list[str],
    default_language: str,
) -> BundleResult:
    copy_tree(source_root, staging)
    injection = inject_sdk(
        staging,
        sdk_path,
        sdk_version=sdk_version,
        sdk_contract_version=sdk_contract_version,
    )
    hashes = tree_hashes(staging)
    critical_path = measure_critical_path(staging, critical, default_language)
    return BundleResult(
        staging=staging,
        files=hashes,
        runtime_hash=runtime_hash_for(hashes),
        injection_report=injection,
        critical_path=critical_path,
    )
