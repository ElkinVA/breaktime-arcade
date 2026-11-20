# BA-ZIP-PREFLIGHT-001 — отчёт

**Дата:** 2026-11-20  
**Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**  
**Исполнитель:** основная сессия / `deepseek-flash[1m]`.  
**Review:** `code-reviewer` и `security-auditor` (`deepseek-v4-pro`,
text-only) — **accept**; M-1/M-2/m-1/m-3/m-6 исправлены; остаток
O-1…O-5/m-4…m-7 — R-034 (non-blocking).  
**Основание:** BA-PLAT-4.2 §2.14.2, §2.14.7; Приложение K (коды).

## 1. Цель и границы

Безопасная предварительная проверка игрового ZIP **без распаковки и
исполнения**: структура архива, пути, типы записей, лимиты, коллизии,
allowlist расширений, SHA-256 пакета и структурированные диагностические
коды для CRM и будущего pipeline.

Не входит: manifest/catalog/locales (BA-GAME-2.2), SDK injection, runtime
bundle, публикация/версии, CSP/nginx/origin, iframe/postMessage,
EventLog/verifier, upload endpoint и модели `GameImportDraft`. Срез не
зависит от BA-SDK-1.1, BA-ENV-1.1 и BA-GAME-2.2.

## 2. Реализация

| Файл | Назначение |
|---|---|
| `apps/pipeline/validation/codes.py` | Стабильные коды, severity, лимиты, `Diagnostic`, `PreflightReport` |
| `apps/pipeline/validation/structure.py` | `preflight_zip(data: bytes) -> PreflightReport`; только чтение central directory |
| `tests/unit/test_zip_preflight.py` | 16 unit tests, включая запрет `extract`/`extractall` |
| `docs/tasks/BA-ZIP-PREFLIGHT-001_PLAN.md` | План, критерии, тестовый план, контракт extraction stage |

Проверки:

- ZIP ≤25 МБ; распакованный ≤100 МБ; коэффициент ≤100:1; ≤2000 записей;
  файл ≤20 МБ.
- Абсолютные пути, `..`, обратные слэши, drive-префиксы, управляющие и
  bidi-символы; NFKC-нормализация (изменение пути — blocker).
- Канонизация: `./`, `//`, пустые и `.`-сегменты, file-vs-dir конфликты —
  blocker; дедуп по каноническому ключу.
- Компонент >255 UTF-8 байт, trailing `.`/пробел, Windows reserved
  (`CON`…`LPT9`).
- Symlink, специальные файлы, шифрование; несоответствие `S_IFDIR`/
  `S_IFREG` и trailing slash — blocker.
- Сверка размеров local header vs central directory
  (`V_ARCHIVE_HEADER_MISMATCH`); data descriptor/ZIP64 пропускаются.
- Дубликаты и регистро-коллизии после NFKC/casefold.
- Allowlist расширений; запрет `.git`, `.DS_Store`, `__MACOSX`,
  `node_modules`, `*.map`.
- SHA-256 пакета; `file_count`, `total_uncompressed`; diagnostics с
  `code`/`severity`/`message`/`file`/`hint`/`meta`.

Модуль не пишет на диск и не вызывает распаковку. Тест
`test_valid_package_passes_without_extraction` подменяет
`zipfile.ZipFile.extract`/`extractall` на исключение.

## 3. Проверки (фактические)

```text
ruff check apps config tests      -> All checks passed
ruff format --check apps config tests -> 344 files already formatted
mypy                              -> Success: no issues found in 320 source files
pytest tests/unit/test_zip_preflight.py -> 16 passed
pytest (full)                     -> 297 passed, 2 skipped, 1 warning
makemigrations --check --dry-run  -> No changes detected
migrate --plan                    -> No planned migration operations
```

Warning — намеренный duplicate entry в тесте дубликатов. Пропуски — E2E без
`BA_E2E`, как и в предыдущем baseline. Модели/миграции не менялись.

## 4. Review

- `code-reviewer` — **accept** исходной реализации: контракт metadata-only
  соблюдён, коды стабильны, тесты покрывают заявленные сценарии.
  Последующие изменения — security-фиксы F-1/F-2/F-3; их проверял
  `security-auditor`.
- `security-auditor` — **ACCEPT**: F-1/F-2/F-3 закрыты в границах
  metadata-only; после первого review найдены M-1 (канонизация/
  дубликаты) и M-2 (type mismatch каталога), m-1…m-6.
  - F-1: NFKC-нормализация и дедуп по каноническому пути/casefold;
  - F-2: сверка local/central размеров + контракт extraction sandbox;
  - F-3: гигиена компонентов пути (255 байт, trailing dot/space, Windows
    reserved).
- После review исправлены: M-1 — канонический ключ и запрет `./`/`//`;
  M-2 — тип записи по trailing slash и блокировка `S_IFDIR` без `/`;
  m-1 — единый `file_count`; m-3 — early return при >2000 записей;
  m-6 — `casefold`. m-4/m-5/m-7 и O-1…O-5 зарегистрированы как R-034;
  m-4 частично покрыт extraction-контрактом. Финальный verdict
  повторной проверки — **ACCEPT**.

Остаточные риски и границы:

- Central directory `file_size` может быть подделан; data descriptor и
  ZIP64 не сверяются без распаковки. Реальная защита от zip bomb и
  исчерпания ресурсов — **BA-ZIP-EXTRACT-001** (R-033).
- Preflight не заменяет антивирус/скан JS и проверку manifest.
- R-034: нет полной длины пути (`PATH_MAX`), allowlist compression method,
  проверки Windows ADS; diagnostics эхо-выводят имя файла, CRM обязана
  экранировать; «25 МБ» трактуется как MiB — уточнить в ТЗ.
- Коды — внутренний контракт CRM; при нормировании Приложения K их
  следует включить в утверждённый словарь.

## 5. Артефакты

SHA-256 на момент отчёта:

```text
932ee0336a7295a45e33f9512d2d4a28d2af505df55373c18c3060379b6fb33a  apps/pipeline/validation/codes.py
444be04ccf96756294763868ce43ce085b145167d9b7d4f9bf3b63390504ee94  apps/pipeline/validation/structure.py
e5fb6b8232cb1dd5ded443263a42c506bbc341e870a728ce4bde89070b27b472  tests/unit/test_zip_preflight.py
```

## 6. Следующий шаг

**BA-ZIP-EXTRACT-001** — изолированная распаковка в worker с лимитами
CPU/RAM/time/disk/network, потоковыми byte caps, CRC, отказом symlink и
повторной валидацией путей. Не зависит от SDK/ENV/GAME. Manifest/catalog/
locales — после выбора BA-GAME-2.2; SDK/iframe/EventLog — после
утверждения BA-SDK-1.1/BA-ENV-1.1.
