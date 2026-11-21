# BA-ZIP-HARDENING-001 (R-035) — отчёт

**Дата:** 2026-11-21
**Статус:** **TECHNICALLY ACCEPTED** (agent, 2026-11-21); независимые
code/security review — **ACCEPT**. Продуктовая приёмка — владелец.
**Исполнитель:** основная сессия / `deepseek-flash[1m]`.
**Основание:** R-035 (`RISK_REGISTER.md`), BA-ZIP-EXTRACT-001/WORKER-001.

## 1. Цель

Закрыть остаток R-035: durability перед atomic rename, method allowlist
(stored/deflate), раздельные коды чтения архива и записи результата.

## 2. Изменения

| Файл | Изменение |
|---|---|
| `apps/pipeline/services/unpack.py` | `X_METHOD_UNSUPPORTED`; `ALLOWED_METHODS={stored,deflate}`; fsync каждого файла; fsync staging/destination dirs; read→`X_ARCHIVE_BAD`, write→`X_IO` |
| `apps/pipeline/services/worker.py` | fsync parent dir для COMPLETED/ATTEMPTS; audit flush+fsync + fsync job dir |
| `apps/pipeline/validation/codes.py`, `structure.py` | `V_METHOD_UNSUPPORTED` в preflight для bzip2/lzma |
| `tests/unit/test_zip_extract.py` | LZMA/bzip2, local/central method mismatch, fsync calls, read error, write error, truncation, dir-fsync failure |
| `tests/unit/test_zip_preflight.py` | bzip2 → `V_METHOD_UNSUPPORTED` |

## 3. Поведение

- ZIP с bzip2/lzma → preflight `V_METHOD_UNSUPPORTED`; extraction дополнительно
  проверяет **local header method** (central directory может лгать) и
  отклоняет `X_METHOD_UNSUPPORTED` до создания staging.
- `BadZipFile` с "CRC" → `X_CRC_MISMATCH`; прочие (truncation/header) →
  `X_ARCHIVE_BAD`.
- Каждый извлечённый файл: `flush` + `os.fsync` перед закрытием.
- `_fsync_directory(staging)` перед `rename`, `_fsync_directory(parent)` после;
  helper best-effort (`O_DIRECTORY`, suppress `OSError`).
- `archive.open`/`source.read` OSError → `X_ARCHIVE_BAD`;
  `sink.write`/flush/fsync OSError → `X_IO`; CRC/структура — прежние коды.
- `_write_text_atomic` (COMPLETED/ATTEMPTS) fsync файла и parent dir;
  `_audit` fsync файла и job dir.

## 4. Проверки

```text
ZIP tests (preflight+extract+worker)                              -> 54 passed
pytest (full)                                                     -> 369 passed, 3 skipped
ruff/mypy                                                          -> clean
benchmark: 2000 files × 1 KiB, fsync, /app ext4                   -> 7.676 s (<50 s)
```

## 5. Остатки

- Directory fsync best-effort: при OSError файлы уже fsynced, каталог может
  быть не долговечен при сбое питания.
- `source.__exit__`/close OSError маппится outer `X_IO` (редкий edge).
- Preflight может принять bzip2, extraction отклоняет — двухслойно.
- Нет fsync каждого промежуточного staging-каталога (best-effort root/parent).
- Performance: fsync на каждый файл; при 2000 файлах возможен overhead,
  проверить в пределах 60-с лимита worker.

## 6. Следующий шаг

Независимый code/security review; затем BA-QUALITY-002.
