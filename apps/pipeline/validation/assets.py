"""Cover/screenshot validation (§2.14.2, BA-GAME-2.2 §11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from apps.pipeline.validation.codes import (
    V_COVER_MISSING,
    V_COVER_SIZE,
    V_SCREENSHOT_COUNT,
    Diagnostic,
)
from apps.pipeline.validation.report import ValidationReport

IMAGE_WIDTH = 1280
IMAGE_HEIGHT = 720
COVER_MAX_BYTES = 200 * 1024
SCREENSHOT_MAX_BYTES = 300 * 1024
MIN_SCREENSHOTS = 2
MAX_SCREENSHOTS = 4


@dataclass(slots=True)
class AssetInfo:
    path: str
    kind: str
    width: int
    height: int
    bytes: int


@dataclass(slots=True)
class AssetsResult:
    cover: AssetInfo | None = None
    screenshots: list[AssetInfo] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _inspect(path: Path, relative_path: str, kind: str) -> AssetInfo | None:
    try:
        size = path.stat().st_size
        with Image.open(path) as image:
            width, height = image.size
    except OSError, UnidentifiedImageError:
        return None
    return AssetInfo(path=relative_path, kind=kind, width=width, height=height, bytes=size)


def validate_assets(root: Path, manifest: dict[str, object]) -> AssetsResult:
    result = AssetsResult()
    report = ValidationReport()
    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        result.diagnostics = report.diagnostics
        return result

    cover_name = assets.get("cover")
    if not isinstance(cover_name, str) or not cover_name:
        report.add(V_COVER_MISSING, "Обложка не указана в манифесте", file="manifest.json")
    else:
        cover_path = root / cover_name
        if not cover_path.is_file():
            report.add(V_COVER_MISSING, "Файл обложки отсутствует", file=cover_name)
        else:
            info = _inspect(cover_path, cover_name, "cover")
            if info is None:
                report.add(V_COVER_MISSING, "Обложка не является изображением", file=cover_name)
            else:
                result.cover = info
                if info.width != IMAGE_WIDTH or info.height != IMAGE_HEIGHT:
                    report.add(
                        V_COVER_SIZE,
                        "Обложка должна быть 1280×720",
                        file=cover_name,
                        meta={"width": info.width, "height": info.height},
                    )
                if info.bytes > COVER_MAX_BYTES:
                    report.add(
                        V_COVER_SIZE,
                        "Обложка превышает 200 КБ",
                        file=cover_name,
                        meta={"bytes": info.bytes, "limit": COVER_MAX_BYTES},
                    )

    screenshots = assets.get("screenshots")
    if not isinstance(screenshots, list):
        report.add(V_SCREENSHOT_COUNT, "Скриншоты не указаны в манифесте", file="manifest.json")
    else:
        if not MIN_SCREENSHOTS <= len(screenshots) <= MAX_SCREENSHOTS:
            report.add(
                V_SCREENSHOT_COUNT,
                "Нужно 2–4 скриншота",
                file="manifest.json",
                meta={"count": len(screenshots)},
            )
        for name in screenshots:
            if not isinstance(name, str) or not name:
                continue
            path = root / name
            if not path.is_file():
                report.add(V_COVER_MISSING, "Файл скриншота отсутствует", file=name)
                continue
            info = _inspect(path, name, "screenshot")
            if info is None:
                report.add(V_COVER_MISSING, "Скриншот не является изображением", file=name)
                continue
            result.screenshots.append(info)
            if info.width != IMAGE_WIDTH or info.height != IMAGE_HEIGHT:
                report.add(
                    V_COVER_SIZE,
                    "Скриншот должен быть 1280×720",
                    file=name,
                    meta={"width": info.width, "height": info.height},
                )
            if info.bytes > SCREENSHOT_MAX_BYTES:
                report.add(
                    V_COVER_SIZE,
                    "Скриншот превышает 300 КБ",
                    file=name,
                    meta={"bytes": info.bytes, "limit": SCREENSHOT_MAX_BYTES},
                )
    result.diagnostics = report.diagnostics
    return result
