# BA-ZIP-EXTRACT-001 — изолированная распаковка ZIP

**Дата:** 2026-11-20  
**Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**
(security-review — accept)  
**Исполнитель:** Flash. **Review:** `security-auditor` (deepseek-v4-pro,
text-only).  
**Основание:** BA-PLAT-4.2 §2.14.2; контракт extraction stage из
`docs/tasks/BA-ZIP-PREFLIGHT-001_PLAN.md`.

## Цель

Распаковать прошедший preflight игровой ZIP в новый каталог без выхода за
его корень, с независимым подсчётом фактических байт, лимитами, проверкой
CRC и атомарной публикацией. Срез не исполняет содержимое пакета и не
зависит от BA-SDK-1.1/BA-ENV-1.1/BA-GAME-2.2.

## Границы

Входит: `apps/pipeline/services/unpack.py` (`extract_zip`), unit-тесты.
Не входит: upload endpoint, модели `GameImportDraft`, manifest/catalog/
locales, SDK injection, runtime bundle, публикация, антивирус/скан JS,
настройка конкретного worker/sandbox-драйвера.

## Требования

- Повторный preflight; при blocker — отказ без создания каталога.
- Потоковая распаковка чанками; независимый счётчик фактических байт
  (не доверять `file_size`, data descriptor, ZIP64).
- Лимиты: 20 МБ/файл, 100 МБ/итог, 2000 файлов; cooperative deadline.
- CRC проверяется при чтении; ошибка → отказ.
- Канонический путь; запрет абсолютных путей, `..`, `./`, `//`, backslash.
- Запрет file-vs-dir и префиксных конфликтов (файл `a` и `a/b`).
- Запись только в новый каталог через `O_EXCL|O_NOFOLLOW`, режим 0600;
  каталоги 0700; staging во временном каталоге рядом с целевым.
- Атомарная публикация: `os.rename(staging, destination)`; существующий
  destination не перезаписывается.
- Очистка staging при любой ошибке; успешный результат — неизменяемый
  список файлов с размером и SHA-256.
- Никакой сети, исполнения, `extract`/`extractall`; worker/sandbox
  обеспечивает CPU/RAM/time/disk/network-лимиты, сервис — byte caps и
  cooperative deadline.

## Критерии приёмки

- Валидный ZIP → файлы, размеры, SHA-256, destination существует.
- Preflight-blocker → `X_PREFLIGHT_REJECTED`, destination отсутствует.
- Превышение per-file/total/files → соответствующий `X_LIMIT_*`.
- Битый CRC → `X_CRC_MISMATCH`.
- Prefix-конфликт → `X_PREFIX_CONFLICT`.
- Deadline → `X_TIMEOUT`.
- Существующий destination → `X_DESTINATION_EXISTS`.
- После любой ошибки нет staging-каталогов.
- Тесты, ruff, mypy; независимый review.

## Тестовый план

`tests/unit/test_zip_extract.py`: valid + content/hash; traversal;
per-file/total/files limits; CRC; prefix conflict; deep path/directory
entries; mutable input; destination exists; deadline; cleanup; no
`extract`/`extractall`. Фактически 11 tests; полный suite 308 passed,
2 skipped; ruff/mypy зелёные; security-review — accept.
