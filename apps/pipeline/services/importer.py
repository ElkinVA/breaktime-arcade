"""End-to-end package import (§2.14.1–§2.14.8).

Flow: intake → preflight → safe extraction → content validation → SDK
injection/runtime bundle → import report → idempotent card/version upsert.
The original ZIP is immutable; the runtime bundle is a separate artifact with
its own hash.
"""

from __future__ import annotations

import json
import shutil
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import (
    Game,
    GameAsset,
    GameTag,
    GameTranslation,
    GameVersion,
    Genre,
    Tag,
)
from apps.i18n.models import Language
from apps.pipeline.models import GameImportDraft, ZipExtractionJob
from apps.pipeline.services.artifacts import (
    ArtifactError,
    ensure_root,
    make_staging_dir,
    store_runtime,
)
from apps.pipeline.services.autotest import run_autotest
from apps.pipeline.services.bundling import build_runtime
from apps.pipeline.services.diff import (
    game_manifest_values,
    split_updates,
    translation_values,
)
from apps.pipeline.services.extraction import (
    ExtractionResult,
    WorkerClientError,
    cancel_job,
    extract_package,
    materialize_result,
    remove_source,
)
from apps.pipeline.services.injection import available_sdks, resolve_sdk
from apps.pipeline.services.intake import intake_zip
from apps.pipeline.services.quota import StorageQuota, StorageQuotaError
from apps.pipeline.validation.assets import AssetsResult, validate_assets
from apps.pipeline.validation.budgets import budget_diagnostics
from apps.pipeline.validation.catalog import validate_catalog
from apps.pipeline.validation.codes import (
    I_DUPLICATE_PACKAGE,
    I_IMPORT_CONFLICT,
    I_IMPORT_CREATED,
    I_IMPORT_UPDATED,
    I_RUNTIME_HASH,
    I_SDK_INJECTED,
    SEVERITY_BLOCKER,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    V_ENCODING,
    V_GENRE_UNKNOWN,
    V_ID_MISMATCH,
    V_LANG_UNKNOWN,
    V_SDK_INCOMPATIBLE,
    V_SDK_MISSING,
    V_VERSION_DUP,
    W_SCORE_RULES_CHANGED,
    W_SEMVER_LOWER,
    W_TAG_NEW,
    W_TAG_UNTRANSLATED,
)
from apps.pipeline.validation.locales import validate_locales
from apps.pipeline.validation.manifest import (
    locate_package_root,
    validate_manifest,
)
from apps.pipeline.validation.report import ValidationReport
from apps.pipeline.validation.security_scan import scan_root
from apps.pipeline.validation.structure import preflight_zip
from apps.pipeline.validation.text import (
    has_bom,
    has_crlf,
    iter_text_files,
    read_text,
    relative,
)

SDK_PACKAGE_PATH = "js/ba-sdk.js"

# One web import writes two copies of the uploaded archive before the worker
# result is cleaned up: the immutable original package and the transient
# upload source.  Reserving both keeps the system-wide cap honest under
# concurrent imports (each in-flight import would otherwise under-reserve by
# one archive).
IMPORT_WRITE_COPIES = 2


@dataclass(slots=True)
class ImportResult:
    status: str
    draft: GameImportDraft
    report: ValidationReport
    game: Game | None = None
    version: GameVersion | None = None
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status != "rejected"


def import_package(
    data: bytes,
    *,
    original_filename: str = "",
    storage_root: Path | None = None,
    runtime_root: Path | None = None,
    sdk_root: Path | None = None,
    uploads_root: Path | None = None,
    artifacts_root: Path | None = None,
    worker_wait_seconds: float | None = None,
    worker_poll_interval: float | None = None,
    created_by: User | None = None,
    target_game: Game | None = None,
) -> ImportResult:
    """Admit one package against the system-wide quota, then import it.

    The reservation is acquired before any write (including the immutable
    original-ZIP store) and released after the import finishes.  A quota
    rejection is non-destructive: it only records a rejected draft/report and
    never touches published runtimes or existing versions.
    """
    # Resolve paths without creating roots: a quota rejection must not touch
    # the runtime or package stores at all.
    storage = Path(storage_root or settings.ZIP_PIPELINE_STORAGE_ROOT)
    runtimes = Path(runtime_root or settings.ZIP_PUBLIC_RUNTIME_ROOT)
    sdk_dir = Path(sdk_root or settings.SDK_SOURCE_ROOT)
    uploads = Path(uploads_root or settings.ZIP_UPLOADS_ROOT)
    artifacts = Path(artifacts_root or settings.ZIP_ARTIFACTS_ROOT)

    quota = StorageQuota.from_settings(
        storage_root=storage,
        uploads_root=uploads,
        artifacts_root=artifacts,
    )
    try:
        reservation = quota.reserve(len(data) * IMPORT_WRITE_COPIES, reason="package-import")
    except StorageQuotaError as exc:
        return _reject_quota(
            data,
            exc,
            original_filename=original_filename,
            created_by=created_by,
        )
    try:
        return _import_package(
            data,
            original_filename=original_filename,
            storage=ensure_root(storage),
            runtimes=ensure_root(runtimes),
            sdk_dir=sdk_dir,
            uploads=uploads,
            artifacts=artifacts,
            worker_wait_seconds=worker_wait_seconds,
            worker_poll_interval=worker_poll_interval,
            created_by=created_by,
            target_game=target_game,
        )
    finally:
        quota.release(reservation)


def _import_package(
    data: bytes,
    *,
    original_filename: str,
    storage: Path,
    runtimes: Path,
    sdk_dir: Path,
    uploads: Path,
    artifacts: Path,
    worker_wait_seconds: float | None,
    worker_poll_interval: float | None,
    created_by: User | None,
    target_game: Game | None,
) -> ImportResult:
    intake = intake_zip(data, storage_root=storage)
    report = ValidationReport(package_hash=intake.package_hash)
    report.extend(intake.diagnostics)
    draft = GameImportDraft.objects.create(
        package_hash=intake.package_hash,
        original_filename=original_filename[:255],
        size_bytes=len(data),
        created_by=created_by,
        diagnostics=[item.as_dict() for item in report.diagnostics],
    )
    if not intake.ok:
        return _reject(draft, report)

    duplicate = _find_duplicate(intake.package_hash, target_game)
    if duplicate is not None:
        report.add(
            I_DUPLICATE_PACKAGE,
            "Пакет с таким package_hash уже импортирован",
            severity=SEVERITY_INFO,
            meta={"version": str(duplicate.id)},
        )
        return _finish_duplicate(draft, duplicate, report, intake.stored_path)

    job = ZipExtractionJob.objects.create(
        draft=draft,
        package_hash=intake.package_hash,
        status=ZipExtractionJob.STATUS_RUNNING,
        started_at=timezone.now(),
    )
    job.source_path = str(Path(uploads) / str(job.id) / "source.zip")
    job.save(update_fields=["source_path", "updated_at"])
    try:
        extraction = extract_package(
            job_id=str(job.id),
            data=data,
            package_hash=intake.package_hash,
            uploads_root=uploads,
            artifacts_root=artifacts,
            wait_seconds=worker_wait_seconds,
            poll_interval=worker_poll_interval,
        )
    except WorkerClientError as exc:
        report.add(
            exc.code,
            exc.message,
            meta=_worker_meta(job, exc.diagnostics),
        )
        _finish_job(
            job,
            status=_job_status_for(exc.code, exc.diagnostics),
            error_code=exc.code,
            task_id=str(exc.diagnostics.get("task_id") or ""),
            diagnostics=_worker_diagnostics(job, None, exc.diagnostics),
        )
        if exc.code == "X_WORKER_TIMEOUT":
            # Tell a still-running worker to stop; the uploads TTL in the
            # worker cleanup task removes the source after it exits.
            cancel_job(str(job.id), uploads)
        elif exc.code != "X_WORKER_UNAVAILABLE":
            # Terminal worker failure/rejection: the source is no longer needed.
            remove_source(str(job.id), uploads)
        return _reject(draft, report)

    work = make_staging_dir(storage / "work")
    try:
        package_dir = work / "package"
        try:
            materialize_result(extraction, package_dir)
        except WorkerClientError as exc:
            report.add(exc.code, exc.message, meta=_worker_meta(job, exc.diagnostics))
            _finish_job(
                job,
                status=ZipExtractionJob.STATUS_FAILED,
                error_code=exc.code,
                attempts=extraction.attempts,
                task_id=extraction.task_id,
                diagnostics=_worker_diagnostics(job, extraction, exc.diagnostics),
            )
            remove_source(str(job.id), uploads)
            return _reject(draft, report)

        _finish_job(
            job,
            status=ZipExtractionJob.STATUS_COMPLETED,
            attempts=extraction.attempts,
            task_id=extraction.task_id,
            diagnostics=_worker_diagnostics(job, extraction),
        )
        job.result_path = str(extraction.result_root)
        job.save(update_fields=["result_path", "updated_at"])
        remove_source(str(job.id), uploads)

        package_root = locate_package_root(package_dir)
        if package_root is None:
            report.add(
                "V_MANIFEST_MISSING",
                "manifest.json не найден или архив содержит несколько корневых каталогов",
            )
            return _reject(draft, report)

        _check_encoding(package_root, report)
        manifest_result = validate_manifest(package_root)
        report.extend(manifest_result.diagnostics)
        manifest = manifest_result.manifest
        if manifest is None:
            return _reject(draft, report)

        supported = _string_list(manifest.get("supportedLanguages"))
        _check_catalog_languages(package_root, manifest, supported, report)
        assets_result = validate_assets(package_root, manifest)
        report.extend(assets_result.diagnostics)
        _check_locales(package_root, supported, report)
        report.extend(scan_root(package_root).diagnostics)

        genre = _resolve_genre(manifest, report)
        languages = _resolve_languages(supported, report)
        sdk_selection = resolve_sdk(str(manifest.get("sdkVersion", "")), sdk_dir)
        if sdk_selection is None:
            report.add(
                V_SDK_INCOMPATIBLE,
                "Нет совместимой официальной версии SDK",
                hint="Проверьте manifest.sdkVersion и доступные версии SDK.",
                meta={"requested": manifest.get("sdkVersion"), "available": _sdk_versions(sdk_dir)},
            )
        sdk_file = package_root / SDK_PACKAGE_PATH
        if not sdk_file.is_file():
            report.add(V_SDK_MISSING, "В пакете отсутствует js/ba-sdk.js", file=SDK_PACKAGE_PATH)

        existing_game = (
            target_game or Game.objects.filter(technical_id=str(manifest.get("id", ""))).first()
        )
        if target_game is not None and (
            target_game.technical_id.lower() != str(manifest.get("id", "")).lower()
        ):
            report.add(
                V_ID_MISMATCH,
                "manifest.id не совпадает с technical_id карточки",
                meta={"manifest_id": manifest.get("id"), "technical_id": target_game.technical_id},
            )
        if existing_game is not None:
            same_semver = existing_game.versions.filter(semver=str(manifest.get("version"))).first()
            if same_semver is not None and same_semver.package_hash != intake.package_hash:
                report.add(
                    V_VERSION_DUP,
                    "Версия с таким semver уже существует",
                    meta={"semver": manifest.get("version")},
                )

        if _has_blockers(report):
            return _reject(draft, report)

        assert sdk_selection is not None  # guarded by blocker above
        assets = manifest.get("assets")
        assets_map = assets if isinstance(assets, dict) else {}
        critical = _string_list(assets_map.get("critical"))
        declared = assets_map.get("criticalPathBytes")
        declared_bytes = declared if isinstance(declared, int) else None
        default_language = str(manifest.get("defaultLanguage", "en"))

        runtime_staging = make_staging_dir(work, prefix=".ba-runtime-")
        bundle = build_runtime(
            package_root,
            runtime_staging,
            sdk_path=sdk_selection.path,
            sdk_version=sdk_selection.version,
            sdk_contract_version=str(manifest.get("protocol", 1)),
            critical=critical,
            default_language=default_language,
        )
        report.extend(
            budget_diagnostics(
                bundle.critical_path,
                declared_bytes,
                warn_bytes=settings.CRITICAL_PATH_WARN_BYTES,
                max_bytes=settings.CRITICAL_PATH_MAX_BYTES,
            )
        )
        if _has_blockers(report):
            return _reject(draft, report)

        autotest = run_autotest(
            bundle.staging,
            manifest=manifest,
            sdk_path=sdk_selection.path,
            critical_path=bundle.critical_path,
            max_critical_bytes=settings.CRITICAL_PATH_MAX_BYTES,
        )
        report.add(
            I_SDK_INJECTED,
            "Официальный SDK внедрён в рабочий бандл",
            severity=SEVERITY_INFO,
            meta={"sdk_version": sdk_selection.version},
        )
        report.add(
            I_RUNTIME_HASH,
            "Вычислен runtime_hash",
            severity=SEVERITY_INFO,
            meta={"runtime_hash": bundle.runtime_hash},
        )

        runtime_game = existing_game or target_game
        runtime_label = (
            runtime_game.host_label
            if runtime_game is not None
            else _host_label(str(manifest.get("id", "")))
        )
        try:
            runtime_dir = store_runtime(
                runtimes,
                bundle.runtime_hash,
                bundle.staging,
                host_label=runtime_label,
            )
        except ArtifactError as exc:
            report.add(exc.code, exc.message)
            return _reject(draft, report)

        try:
            game, version, conflicts = _persist(
                manifest=manifest,
                genre=genre,
                languages=languages,
                assets_result=assets_result,
                package_root=package_root,
                target_game=target_game,
                existing_game=existing_game,
                package_hash=intake.package_hash,
                runtime_hash=bundle.runtime_hash,
                sdk_version=sdk_selection.version,
                sdk_contract_version=str(manifest.get("protocol", 1)),
                size_bytes=len(data),
                critical_declared=declared_bytes,
                critical_measured=bundle.critical_path.measured_bytes,
                report=report,
                injection_report=bundle.injection_report.as_dict(),
                e2e_report=autotest.report,
                created_by=created_by,
            )
        except IntegrityError:
            duplicate = _find_duplicate(intake.package_hash, target_game)
            if duplicate is not None:
                return _finish_duplicate(draft, duplicate, report, intake.stored_path)
            report.add(V_VERSION_DUP, "Версия с таким semver уже существует")
            return _reject(draft, report)
        except OSError:
            report.add("X_ARTIFACT_IO", "Не удалось сохранить ассеты игры")
            return _reject(draft, report)

        status = "created" if version.import_report.get("created") else "updated"
        draft.status = GameImportDraft.STATUS_IMPORTED
        draft.manifest = manifest
        draft.validation_report = report.as_dict()
        draft.import_report = version.import_report
        draft.injection_report = version.injection_report
        draft.e2e_report = version.e2e_report
        draft.conflicts = conflicts
        draft.diagnostics = [item.as_dict() for item in report.diagnostics]
        draft.game = game
        draft.version = version
        draft.package_path = str(intake.stored_path or "")
        draft.runtime_path = str(runtime_dir)
        draft.save()
        return ImportResult(
            status=status,
            draft=draft,
            report=report,
            game=game,
            version=version,
            conflicts=conflicts,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _reject_quota(
    data: bytes,
    error: StorageQuotaError,
    *,
    original_filename: str,
    created_by: User | None,
) -> ImportResult:
    """Record a non-destructive quota rejection without storing the package."""
    preflight = preflight_zip(data)
    report = ValidationReport(package_hash=preflight.package_hash)
    report.extend(preflight.diagnostics)
    report.add(error.code, error.message, meta=error.diagnostics)
    draft = GameImportDraft.objects.create(
        package_hash=preflight.package_hash,
        original_filename=original_filename[:255],
        size_bytes=len(data),
        created_by=created_by,
        diagnostics=[item.as_dict() for item in report.diagnostics],
    )
    return _reject(draft, report)


def _sdk_versions(sdk_dir: Path) -> list[str]:
    return [item.version for item in available_sdks(sdk_dir)]


def _find_duplicate(package_hash: str, target_game: Game | None) -> GameVersion | None:
    query = GameVersion.objects.select_related("game").filter(package_hash=package_hash)
    if target_game is not None:
        query = query.filter(game_id=target_game.id)
    return query.first()


def _has_blockers(report: ValidationReport) -> bool:
    return any(item.severity == SEVERITY_BLOCKER for item in report.diagnostics)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _check_encoding(root: Path, report: ValidationReport) -> None:
    for path in iter_text_files(root):
        name = relative(root, path)
        if has_bom(path):
            report.add(V_ENCODING, "Файл содержит UTF-8 BOM", file=name)
        if has_crlf(path):
            report.add(V_ENCODING, "Файл содержит CRLF; требуется LF", file=name)


def _check_catalog_languages(
    root: Path,
    manifest: dict[str, Any],
    supported: list[str],
    report: ValidationReport,
) -> None:
    assets = manifest.get("assets")
    screenshots = assets.get("screenshots") if isinstance(assets, dict) else None
    count = len(screenshots) if isinstance(screenshots, list) else 0
    report.extend(validate_catalog(root, supported, count).diagnostics)


def _check_locales(
    root: Path,
    supported: list[str],
    report: ValidationReport,
) -> None:
    report.extend(validate_locales(root, supported).diagnostics)


def _resolve_genre(manifest: dict[str, Any], report: ValidationReport) -> Genre | None:
    code = manifest.get("genre")
    if not isinstance(code, str):
        report.add(V_GENRE_UNKNOWN, "Жанр не указан")
        return None
    genre = Genre.objects.filter(code=code).first()
    if genre is None:
        report.add(V_GENRE_UNKNOWN, f"Неизвестный жанр «{code}»", meta={"genre": code})
    return genre


def _resolve_languages(
    supported: list[str],
    report: ValidationReport,
) -> dict[str, Language]:
    languages: dict[str, Language] = {}
    for code in supported:
        language = Language.objects.filter(code=code).first()
        if language is None:
            report.add(V_LANG_UNKNOWN, f"Неизвестный язык «{code}»", meta={"language": code})
        else:
            languages[code] = language
    return languages


def _reject(draft: GameImportDraft, report: ValidationReport) -> ImportResult:
    draft.status = GameImportDraft.STATUS_REJECTED
    draft.validation_report = report.as_dict()
    draft.diagnostics = [item.as_dict() for item in report.diagnostics]
    draft.save()
    return ImportResult(status="rejected", draft=draft, report=report)


def _finish_duplicate(
    draft: GameImportDraft,
    version: GameVersion,
    report: ValidationReport,
    stored_path: Path | None,
) -> ImportResult:
    draft.status = GameImportDraft.STATUS_IMPORTED
    draft.game = version.game
    draft.version = version
    draft.validation_report = report.as_dict()
    draft.diagnostics = [item.as_dict() for item in report.diagnostics]
    draft.package_path = str(stored_path or "")
    draft.save()
    return ImportResult(
        status="duplicate",
        draft=draft,
        report=report,
        game=version.game,
        version=version,
    )


def _persist(
    *,
    manifest: dict[str, Any],
    genre: Genre | None,
    languages: dict[str, Language],
    assets_result: AssetsResult,
    package_root: Path,
    target_game: Game | None,
    existing_game: Game | None,
    package_hash: str,
    runtime_hash: str,
    sdk_version: str,
    sdk_contract_version: str,
    size_bytes: int,
    critical_declared: int | None,
    critical_measured: int,
    report: ValidationReport,
    injection_report: dict[str, Any],
    e2e_report: dict[str, Any],
    created_by: User | None,
) -> tuple[Game, GameVersion, list[dict[str, Any]]]:
    conflicts: list[dict[str, Any]] = []
    tags_created: list[str] = []
    created = existing_game is None and target_game is None
    with transaction.atomic():
        if existing_game is not None:
            game = Game.objects.select_for_update().get(pk=existing_game.pk)
        else:
            if genre is None:
                raise IntegrityError("genre is required")
            game = Game.objects.create(
                technical_id=str(manifest["id"]),
                host_label=_host_label(str(manifest["id"])),
                slug=_host_label(str(manifest["id"])),
                primary_genre=genre,
            )

        overridden = {str(item) for item in (game.overridden_fields or [])}
        incoming = game_manifest_values(manifest)
        current = {key: getattr(game, key) for key in incoming}
        updates, game_conflicts = split_updates(
            scope="game", current=current, incoming=incoming, overridden=overridden
        )
        conflicts.extend(game_conflicts)
        for field_name, value in updates.items():
            setattr(game, field_name, value)

        if genre is not None:
            if "primary_genre" in overridden:
                if game.primary_genre_id != genre.id:
                    conflicts.append(
                        {
                            "scope": "game",
                            "field": "primary_genre",
                            "current": game.primary_genre.code,
                            "incoming": genre.code,
                            "resolution": "keep",
                        }
                    )
            else:
                game.primary_genre = genre

        old_direction = game.score_direction
        old_schema = game.score_schema_version
        _apply_platform_fields(game, manifest)
        if not created and (
            old_direction != game.score_direction or old_schema != game.score_schema_version
        ):
            report.add(
                W_SCORE_RULES_CHANGED,
                "Изменились правила счёта; до публикации требуется решение об эпохе рекордов",
                severity=SEVERITY_WARNING,
            )

        if "tags" not in overridden:
            game.tag_links.all().delete()
            tag_objects: list[Tag] = []
            for code in _string_list(manifest.get("tags")):
                tag, tag_created = Tag.objects.get_or_create(code=code)
                tag_objects.append(tag)
                if tag_created:
                    tags_created.append(code)
                    report.add(
                        W_TAG_NEW,
                        f"Создан новый тег «{code}»",
                        severity=SEVERITY_WARNING,
                        meta={"tag": code},
                    )
                    report.add(
                        W_TAG_UNTRANSLATED,
                        f"Тег «{code}» требует перевода",
                        severity=SEVERITY_WARNING,
                        meta={"tag": code},
                    )
            GameTag.objects.bulk_create(
                [GameTag(game=game, tag=tag) for tag in tag_objects], ignore_conflicts=True
            )
        else:
            current_tags = set(game.tags.values_list("code", flat=True))
            incoming_tags = set(_string_list(manifest.get("tags")))
            if current_tags != incoming_tags:
                conflicts.append(
                    {
                        "scope": "game",
                        "field": "tags",
                        "current": sorted(current_tags),
                        "incoming": sorted(incoming_tags),
                        "resolution": "keep",
                    }
                )

        game.save()
        if not created:
            previous = game.versions.order_by("-created_at").first()
            if previous is not None and _semver_lt(str(manifest.get("version")), previous.semver):
                report.add(
                    W_SEMVER_LOWER,
                    "Версия ниже текущей",
                    severity=SEVERITY_WARNING,
                    meta={"semver": manifest.get("version"), "current": previous.semver},
                )

        translations_report = _apply_translations(game, languages, package_root, conflicts)
        if "assets" in overridden:
            conflicts.append({"scope": "game", "field": "assets", "resolution": "keep"})
        if conflicts:
            report.add(
                I_IMPORT_CONFLICT,
                "Есть конфликты с переопределениями CRM",
                severity=SEVERITY_INFO,
                meta={"count": len(conflicts)},
            )
        report.add(
            I_IMPORT_CREATED if created else I_IMPORT_UPDATED,
            "Карточка создана" if created else "Карточка обновлена",
            severity=SEVERITY_INFO,
        )

        assets_owned_by_crm = "assets" in overridden
        assets_report = {
            "created": 0
            if assets_owned_by_crm
            else (1 if assets_result.cover is not None else 0) + len(assets_result.screenshots),
            "cover": None
            if assets_owned_by_crm
            else (assets_result.cover.path if assets_result.cover is not None else None),
            "overridden": assets_owned_by_crm,
        }
        import_report: dict[str, Any] = {
            "created": created,
            "status": "created" if created else "updated",
            "updated_fields": sorted(updates),
            "conflicts": conflicts,
            "tags_created": tags_created,
            "translations": translations_report,
            "assets": assets_report,
            "runtime_hash": runtime_hash,
            "package_hash": package_hash,
        }
        version = GameVersion.objects.create(
            game=game,
            semver=str(manifest["version"]),
            package_hash=package_hash,
            runtime_hash=runtime_hash,
            sdk_version=sdk_version,
            sdk_contract_version=sdk_contract_version,
            size_bytes=size_bytes,
            manifest=manifest,
            entry_path=str(manifest.get("entry", "index.html")),
            critical_path_bytes_declared=critical_declared,
            critical_path_bytes_measured=critical_measured,
            supported_languages=_string_list(manifest.get("supportedLanguages")),
            claimed_verification=_claimed_verification(manifest),
            validation_report=report.as_dict(),
            import_report=import_report,
            injection_report=injection_report,
            e2e_report=e2e_report,
            created_by=created_by,
        )
        if not assets_owned_by_crm:
            _import_assets(game, version, package_root, assets_result, languages)
    return game, version, conflicts


def _apply_platform_fields(game: Game, manifest: dict[str, Any]) -> None:
    limits = manifest.get("limits") if isinstance(manifest.get("limits"), dict) else {}
    if isinstance(limits, dict):
        game.min_session_seconds = _int_or(limits.get("minPlaytimeSeconds"), 15)
        game.max_session_seconds = _int_or(limits.get("maxSessionSeconds"), 1800)
        game.pause_on_blur = bool(limits.get("pauseOnBlur", True))
    score = manifest.get("score") if isinstance(manifest.get("score"), dict) else {}
    if isinstance(score, dict):
        game.score_type = str(score.get("type", "integer"))
        game.score_unit = str(score.get("unit", "points"))
        game.score_direction = str(score.get("direction", "higher_is_better"))
        game.score_min_value = _int_or(score.get("minValue"), 0)
        game.score_max_value = _int_or(score.get("maxValue"), 100000)
        game.score_schema_version = _int_or(score.get("schemaVersion"), 1)
    capabilities = manifest.get("capabilities")
    if isinstance(capabilities, dict):
        game.capabilities = capabilities
    verification = manifest.get("verification")
    if isinstance(verification, dict) and isinstance(verification.get("profile"), dict):
        game.verification_profile = verification["profile"]
    game.default_language = str(manifest.get("defaultLanguage", "en"))


def _apply_translations(
    game: Game,
    languages: dict[str, Language],
    package_root: Path,
    conflicts: list[dict[str, Any]],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for code, language in languages.items():
        path = package_root / "catalog" / f"{code}.json"
        if not path.is_file():
            continue
        data = json.loads(read_text(path))
        if not isinstance(data, dict):
            continue
        values = translation_values(data)
        translation = GameTranslation.objects.filter(game=game, language=language).first()
        if translation is None:
            GameTranslation.objects.create(
                game=game,
                language=language,
                slug=game.slug,
                **values,
            )
            result[code] = "created"
            continue
        overridden = {str(item) for item in (translation.overridden_fields or [])}
        current = {field: getattr(translation, field) for field in values}
        updates, field_conflicts = split_updates(
            scope=f"translation:{code}",
            current=current,
            incoming=values,
            overridden=overridden,
        )
        conflicts.extend(field_conflicts)
        for field_name, value in updates.items():
            setattr(translation, field_name, value)
        if updates:
            translation.save(update_fields=[*updates, "updated_at"])
        result[code] = "updated" if updates else "unchanged"
    return result


def _import_assets(
    game: Game,
    version: GameVersion,
    package_root: Path,
    assets: AssetsResult,
    languages: dict[str, Language],
) -> None:
    catalog_alts = _catalog_alts(package_root, languages)
    existing = GameAsset.objects.filter(
        game=game, type__in=[GameAsset.TYPE_COVER, GameAsset.TYPE_SCREENSHOT]
    )
    for asset in existing:
        if asset.file:
            asset.file.delete(save=False)
    existing.delete()
    if assets.cover is not None:
        data = (package_root / assets.cover.path).read_bytes()
        cover_alt = {code: alts.get("coverAlt", "") for code, alts in catalog_alts.items()}
        asset = GameAsset.objects.create(
            game=game,
            version=version,
            type=GameAsset.TYPE_COVER,
            file=ContentFile(
                data, name=f"{game.technical_id}-cover{Path(assets.cover.path).suffix}"
            ),
            alt=cover_alt,
            sort_order=0,
            width=assets.cover.width,
            height=assets.cover.height,
            bytes=assets.cover.bytes,
        )
        _make_public_media(asset)
    for index, screenshot in enumerate(assets.screenshots):
        data = (package_root / screenshot.path).read_bytes()
        alt = {
            code: _alt_at(alts.get("screenshotAlts"), index) for code, alts in catalog_alts.items()
        }
        asset = GameAsset.objects.create(
            game=game,
            version=version,
            type=GameAsset.TYPE_SCREENSHOT,
            file=ContentFile(
                data, name=f"{game.technical_id}-screen-{index + 1}{Path(screenshot.path).suffix}"
            ),
            alt=alt,
            sort_order=index + 1,
            width=screenshot.width,
            height=screenshot.height,
            bytes=screenshot.bytes,
        )
        _make_public_media(asset)


def _make_public_media(asset: GameAsset) -> None:
    """Covers/screenshots are public; upload defaults are private (0750/0640)."""
    with suppress(OSError, ValueError, NotImplementedError):
        stored = Path(asset.file.path)
        stored.chmod(0o644)
        media_root = Path(settings.MEDIA_ROOT).resolve()
        directory = stored.parent.resolve()
        while directory == media_root or media_root in directory.parents:
            directory.chmod(0o755)
            if directory == media_root:
                break
            directory = directory.parent


def _catalog_alts(package_root: Path, languages: dict[str, Language]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for code in languages:
        path = package_root / "catalog" / f"{code}.json"
        if not path.is_file():
            continue
        data = json.loads(read_text(path))
        if isinstance(data, dict):
            result[code] = data
    return result


def _alt_at(value: object, index: int) -> str:
    if isinstance(value, list) and index < len(value) and isinstance(value[index], str):
        return str(value[index])
    return ""


def _claimed_verification(manifest: dict[str, Any]) -> str:
    leaderboard = manifest.get("leaderboard")
    if isinstance(leaderboard, dict):
        return str(leaderboard.get("claimedVerification", ""))
    return ""


def _int_or(value: object, default: int) -> int:
    return int(value) if isinstance(value, (int, float)) else default


def _host_label(technical_id: str) -> str:
    return technical_id.lower().replace("_", "-")[:63]


def _semver_lt(candidate: str, current: str) -> bool:
    from packaging.version import InvalidVersion, Version

    try:
        return Version(candidate) < Version(current)
    except InvalidVersion:
        return False


def _job_status_for(code: str, diagnostics: dict[str, Any]) -> str:
    worker_status = diagnostics.get("worker_status")
    if code == "X_WORKER_TIMEOUT" or worker_status == "timeout":
        return ZipExtractionJob.STATUS_TIMEOUT
    if code == "X_CANCELLED" or worker_status == "cancelled":
        return ZipExtractionJob.STATUS_CANCELLED
    if code == "X_WORKER_UNAVAILABLE":
        return ZipExtractionJob.STATUS_FAILED
    return ZipExtractionJob.STATUS_REJECTED


def _worker_meta(job: ZipExtractionJob, diagnostics: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {"job_id": str(job.id)}
    worker_status = diagnostics.get("worker_status")
    if isinstance(worker_status, str):
        meta["worker_status"] = worker_status
    exception = diagnostics.get("exception")
    if isinstance(exception, str):
        meta["exception"] = exception
    return meta


def _worker_diagnostics(
    job: ZipExtractionJob,
    extraction: ExtractionResult | None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"job_id": str(job.id)}
    if extraction is not None:
        payload.update(
            {
                "status": extraction.status,
                "package_hash": extraction.package_hash,
                "total_bytes": extraction.total_bytes,
                "file_count": extraction.file_count,
                "attempts": extraction.attempts,
            }
        )
    if error:
        payload["error"] = dict(error)
    return payload


def _finish_job(
    job: ZipExtractionJob,
    *,
    status: str,
    error_code: str = "",
    attempts: int = 0,
    task_id: str = "",
    diagnostics: dict[str, Any] | None = None,
) -> None:
    job.status = status
    job.error_code = error_code
    job.attempts = attempts
    job.task_id = task_id
    job.diagnostics = diagnostics or {}
    job.finished_at = timezone.now()
    # The web outcome is authoritative: a genuinely slow import that finishes
    # after the reaper marked it X_JOB_STALE intentionally overwrites that row.
    job.save()


__all__ = ["ImportResult", "import_package"]
