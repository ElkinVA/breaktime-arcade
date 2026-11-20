# BA-ZIP-PREFLIGHT-001 — безопасная проверка ZIP (metadata-only)

**Дата:** 2026-11-20  
**Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** (review — accept)  
**Исполнитель:** Flash. **Review:** `code-reviewer`/`security-auditor`
(deepseek-v4-pro, text-only).  
**Основание:** BA-PLAT-4.2 §2.14.2, §2.14.7; Приложение K (коды).

## Цель

Дать CRM и будущему pipeline безопасную предварительную проверку игрового
ZIP **без распаковки и исполнения**: структура, пути, типы записей, лимиты,
коллизии, допустимые расширения, SHA-256 пакета и структурированные
диагностические коды. Срез не зависит от BA-SDK-1.1/BA-ENV-1.1/BA-GAME-2.2.

## Границы

Входит: `apps/pipeline/validation/structure.py` (валидатор),
`apps/pipeline/validation/codes.py` (коды/диагностика), unit-тесты.
Не входит: manifest/catalog/locales-схемы (BA-GAME), SDK injection,
runtime bundle, публикация/версии, CSP/nginx/origin, iframe/postMessage,
EventLog/verifier, upload endpoint и модели `GameImportDraft`.

## Требования (§2.14.2)

ZIP ≤25 МБ; распакованный ≤100 МБ; коэффициент ≤100:1; ≤2000 файлов;
файл ≤20 МБ; только относительные пути, без `..`, абсолютных, symlink,
коллизий; allowlist расширений; `.git`, `.DS_Store`, `__MACOSX`,
`node_modules`, `*.map` отклоняются; SHA-256 пакета; отчёт с кодом,
severity, файлом, сообщением, подсказкой.

## Критерии приёмки

- Валидный пакет → `ok`, hash 64 hex, file_count/total_uncompressed.
- Path traversal/absolute/backslash/drive/control/bidi → blocker.
- Symlink/специальные записи/шифрование → blocker.
- Дубликаты и регистровые коллизии → blocker.
- Недопустимое расширение/служебные файлы → blocker.
- 25 МБ/2000/20 МБ/100 МБ/100:1 — blocker.
- Нет записи на диск; `extract`/`extractall` не вызываются (тест).
- Понятные диагностические коды; `PreflightReport.as_dict()` для CRM.
- lint/types/full suite; независимый review.

## Тестовый план

`tests/unit/test_zip_preflight.py`: valid + no-extraction monkeypatch;
bad/empty/oversized/too many; traversal/absolute/backslash/control/bidi;
symlink; duplicate/case collision; extensions/service files; encrypted;
file >20 МБ + ratio; total >100 МБ; structured diagnostics; forged local/
central sizes; NFKC; Windows reserved/trailing dot/space.

Фактически: 16 tests passed; полный suite — 297 passed, 2 skipped;
ruff/mypy — зелёные; code-reviewer/security-auditor — **accept**;
остаток O-1…O-5/m-4…m-7 — R-034 (non-blocking).

## Контракт extraction stage (BA-ZIP-EXTRACT-001)

Metadata-only preflight не является границей безопасности распаковки.
Будущая стадия обязана:

- распаковывать потоково в отдельный пустой каталог с независимым счётчиком
  фактических байт (не доверять `file_size` из central/local header,
  data descriptor и ZIP64), обрывать при 20 МБ/файл и 100 МБ/итог;
- не преаллоцировать буферы по непроверенным размерам; ограничивать память
  декомпрессора (или явный allowlist методов stored/deflate);
- проверять CRC и фактический размер каждого файла;
- отклонять symlink/hardlink/спецфайлы по материализованному типу и
  повторно валидировать канонический путь (пустые/`.` сегменты, дубликаты,
  file-vs-dir и префиксные конфликты), не допуская выхода за корень;
- повторно проверять allowlist расширений и служебные пути по имени;
- публиковать результат атомарно только после успешной проверки;
- выполняться в worker/sandbox с лимитами CPU, RAM, времени, диска и без
  сети; временный каталог очищать при успехе и ошибке;
- не исполнять содержимое пакета и не публиковать его до прохождения
  manifest/catalog/locales и security-сканов.

## Риски

- Central directory `file_size` может быть подделан; реальные размеры/CRC
  проверяются на extraction stage в sandbox (лимиты CPU/RAM/time/disk).
- Metadata-only не заменяет антивирус/скан JS — это следующие стадии.
- Коды добавляются в словарь Приложения K при нормировании; сейчас
  внутренний контракт CRM.
