# BA-ZIP-EXTRACT-001 — отчёт

**Дата:** 2026-11-20  
**Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**  
**Исполнитель:** основная сессия / `deepseek-flash[1m]`.  
**Review:** `security-auditor` (`deepseek-v4-pro`, text-only) — **accept**
после исправления MINOR-1…6/A/B; остаток R-035 (durability/error
taxonomy) — non-blocking.  
**Основание:** BA-PLAT-4.2 §2.14.2; extraction-контракт
`docs/tasks/BA-ZIP-PREFLIGHT-001_PLAN.md`.

## 1. Цель и границы

Материализовать прошедший preflight ZIP в новый каталог без выхода за его
корень и без исполнения содержимого. Срез не зависит от BA-SDK-1.1,
BA-ENV-1.1 и BA-GAME-2.2.

Не входит: upload endpoint, модели `GameImportDraft`, manifest/catalog/
locales, SDK injection, runtime bundle, публикация, антивирус/скан JS,
OS-level sandbox worker.

## 2. Реализация

| Файл | Назначение |
|---|---|
| `apps/pipeline/services/unpack.py` | `extract_zip`: повторный preflight, streaming, лимиты, CRC, пути, atomic rename, cleanup |
| `tests/unit/test_zip_extract.py` | 11 unit tests |
| `docs/tasks/BA-ZIP-EXTRACT-001_PLAN.md` | План, критерии, тестовый план |

Ключевые свойства:

- повторный `preflight_zip`; blocker → `X_PREFLIGHT_REJECTED`, каталог не
  создаётся;
- чтение чанками 64 КиБ; независимый счётчик фактических байт;
- лимиты 20 МБ/файл, 100 МБ/итог, 2000 записей; вызывающий может только
  ужесточить;
- CRC проверяется `zipfile`; `BadZipFile` → `X_CRC_MISMATCH`;
- фактический размер сверяется с заголовком → `X_SIZE_MISMATCH`;
- канонические пути, запрет `..`, `.`, `//`, backslash, absolute, drive,
  control/bidi, >255 байт/компонент, >1024 байт/путь, >64 компонентов;
- file-vs-dir, prefix-конфликты, дубликаты/регистровые коллизии;
- staging 0700 рядом с destination; файлы `O_CREAT|O_EXCL|O_NOFOLLOW`,
  0600; атомарный `rename`; существующий destination не перезаписывается;
- очистка staging при любой ошибке;
- cooperative deadline (абсолютный `time.monotonic`); CPU/RAM/disk/network
  — ответственность worker (BA-ZIP-WORKER-001);
- `extract`/`extractall` не вызываются (тест).

## 3. Проверки

```text
pytest tests/unit/test_zip_extract.py -> 11 passed
pytest (full)                     -> 308 passed, 2 skipped, 1 warning
ruff check apps config tests      -> All checks passed
ruff format --check               -> 345 files already formatted
mypy                              -> Success: no issues found in 320 source files
```

Покрыто: valid + SHA-256, preflight rejection, symlink preflight, per-file/
total/file-count limits, CRC, prefix conflict file+file и file+dir,
deep path/directory entries, mutable input, destination exists,
deadline/cleanup.

## 4. Review

`security-auditor` — **ACCEPT**: blocker/major нет; условия —
усилить caps на длину/глубину пути и число directory-entry, deadline в
цикле каталогов, устойчивый cleanup, error-taxonomy/errno-маппинг,
зарегистрировать control/bidi и mutable-input риски.

Исправлено: `_parts` ограничивает путь 1024 байтами и 64 компонентами,
запрещает control/C1/bidi/ZW; `_ensure_dir` и mkdir/mkdtemp обёрнуты в
`X_IO`; лимит считает сырые entry; deadline в цикле каталогов; rename
маппит EEXIST/ENOTEMPTY в `X_DESTINATION_EXISTS`, прочие — `X_IO`;
`RuntimeError/EOFError/LZMAError` → `X_ARCHIVE_BAD`; `data` копируется в
`bytes`; cleanup через `contextlib.suppress`; лишний chmod убран.

Остаток: R-035 (fsync/durability, единый `X_IO` для чтения bzip2 и записи,
method allowlist) — non-blocking для текущего среза; worker isolation —
BA-ZIP-WORKER-001.

## 5. Артефакты

```text
3edf7a3b3cfd7ca068ad5c87cb40e7dd2536644e06547f64e95bbccf9988042f  apps/pipeline/services/unpack.py
8fe412b45bc84045544025af1612d1b6b7c7ba13a181d4e2ce4160a91b7ba3ee  tests/unit/test_zip_extract.py
```

## 6. Следующий шаг

**BA-ZIP-WORKER-001** — OS-level sandbox: CPU/RAM/time/disk/network,
очередь, отмена, аудит; затем manifest/catalog/locales после BA-GAME-2.2.
