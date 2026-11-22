"""Official SDK selection and injection (§2.14.3).

The packaged ``js/ba-sdk.js`` is never trusted: the platform always replaces
it with an official build compatible with ``manifest.sdkVersion`` and
``manifest.protocol``. If no compatible build exists the package is rejected
with ``V_SDK_INCOMPATIBLE``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

SDK_FILE = "js/ba-sdk.js"


@dataclass(frozen=True, slots=True)
class SdkSelection:
    version: str
    path: Path


@dataclass(frozen=True, slots=True)
class InjectionReport:
    path: str
    sdk_version: str
    sdk_contract_version: str
    before_sha256: str | None
    after_sha256: str
    before_bytes: int
    after_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sdk_version": self.sdk_version,
            "sdk_contract_version": self.sdk_contract_version,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
        }


def available_sdks(sdk_root: Path) -> list[SdkSelection]:
    result: list[SdkSelection] = []
    if not sdk_root.is_dir():
        return result
    for path in sorted(sdk_root.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        sdk_file = path / "ba-sdk.js"
        if not sdk_file.is_file():
            continue
        try:
            Version(path.name)
        except InvalidVersion:
            continue
        result.append(SdkSelection(version=path.name, path=sdk_file))
    return sorted(result, key=lambda item: Version(item.version))


def _caret_bounds(version: Version) -> tuple[Version, Version]:
    if version.major > 0:
        return version, Version(f"{version.major + 1}.0.0")
    if version.minor > 0:
        return version, Version(f"0.{version.minor + 1}.0")
    return version, Version(f"0.0.{version.micro + 1}")


def _tilde_bounds(version: Version) -> tuple[Version, Version]:
    return version, Version(f"{version.major}.{version.minor + 1}.0")


def _parse_range(value: str) -> list[tuple[str, Version]] | None:
    """Return comparison predicates; ``None`` means unparseable."""
    text = value.strip()
    if not text or text == "*":
        return []
    if text.startswith("^"):
        try:
            lower, upper = _caret_bounds(Version(text[1:]))
        except InvalidVersion:
            return None
        return [(">=", lower), ("<", upper)]
    if text.startswith("~"):
        try:
            lower, upper = _tilde_bounds(Version(text[1:]))
        except InvalidVersion:
            return None
        return [(">=", lower), ("<", upper)]
    predicates: list[tuple[str, Version]] = []
    for token in text.replace(",", " ").split():
        operator = ""
        number = token
        for candidate in (">=", "<=", "==", ">", "<", "="):
            if token.startswith(candidate):
                operator = candidate
                number = token[len(candidate) :]
                break
        try:
            parsed = Version(number)
        except InvalidVersion:
            return None
        predicates.append((operator or "==", parsed))
    return predicates or None


def _satisfies(version: Version, predicates: list[tuple[str, Version]]) -> bool:
    for operator, bound in predicates:
        if operator == ">=" and not version >= bound:
            return False
        if operator == ">" and not version > bound:
            return False
        if operator == "<=" and not version <= bound:
            return False
        if operator == "<" and not version < bound:
            return False
        if operator == "==":
            if len(bound.release) == 2:
                if (version.major, version.minor) != (bound.major, bound.minor):
                    return False
            elif version != bound:
                return False
    return True


def resolve_sdk(sdk_range: str, sdk_root: Path) -> SdkSelection | None:
    predicates = _parse_range(sdk_range)
    if predicates is None:
        return None
    candidates = [
        item for item in available_sdks(sdk_root) if _satisfies(Version(item.version), predicates)
    ]
    return candidates[-1] if candidates else None


def inject_sdk(
    runtime_root: Path,
    sdk_path: Path,
    *,
    sdk_version: str,
    sdk_contract_version: str,
) -> InjectionReport:
    target = runtime_root / SDK_FILE
    before = target.read_bytes() if target.is_file() else b""
    official = sdk_path.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(official)
    return InjectionReport(
        path=SDK_FILE,
        sdk_version=sdk_version,
        sdk_contract_version=sdk_contract_version,
        before_sha256=hashlib.sha256(before).hexdigest() if before else None,
        after_sha256=hashlib.sha256(official).hexdigest(),
        before_bytes=len(before),
        after_bytes=len(official),
    )
