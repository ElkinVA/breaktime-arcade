# Внешний аудит 2026-11-25 — статус разбора

Источник: отчёт внешней модели, переданный владельцем 2026-11-25.
Снимок аудита: `47e5f75` (docs над кодовым `40264c2`). Запись фиксирует, что
принято в работу, что исправлено и что остаётся owner-gated. Наличие записи
не является продуктовой приёмкой.

## Принятые P1

| Finding | Решение | Статус |
|---|---|---|
| Импорт меняет опубликованную игру до publish | Временный blocker `V_PUBLISHED_UPDATE_BLOCKED` для `Game.PUBLISHED_STATUSES`, re-check под row lock | **Исправлено** `1763554`, `cc9923b`; draft isolation — `ARCADE-IMPORT-DRAFT-ISOLATION-001` |
| Статический autotest проходит publish gate | `autotest_passed`: `passed` + в production `playwright=true`; rollback ранее опубликованных версий освобождён | **Исправлено** `50f9135`, `d8c5d9f`; browser runner/override — `ARCADE-BROWSER-AUTOTEST-RUNNER-001` |
| Пустой `eventLog.events=[]` → heuristic_validated | `empty_event_log` → quarantine, исключение из leaderboard | **Исправлено** `154de78` |
| AI HQ child process не OS sandbox | Требует смены границы безопасности/полномочий агентов | **OWNER-GATED**, `ARCADE-AI-HQ-OS-SANDBOX-001` |
| ZIP-worker и Celery workers делят Redis broker без ACL | Требует отдельного broker/ACL и проверки Celery-совместимости | **OWNER-GATED**, `ARCADE-REDIS-BROKER-ISOLATION-001` |

## Принятые P2/P3

| Finding | Решение | Статус |
|---|---|---|
| pagehide может закрыть сессию во время in-flight submit | pagehide пропускает close при pending submit; submit сам завершает сессию | **Исправлено** `64d7149`; server-side atomic terminal op — остаток |
| Submit PB lookup без `is_public` | Модерационного скрытия строк ещё нет; фильтр преждевременен (может «разскрыть» строку) | **OWNER/DESIGN**, `ARCADE-PB-ISPUBLIC-001` |
| Email reset race, submit/restart residuals, eventLog boundary, ratings catch-up, staging/restore | Мелкие/инфраструктурные остатки | Заведены в `BACKLOG.md` |

## Что аудит подтвердил положительно

Сессии/результаты, idempotency, throttling, streaming ZIP, изоляция worker
по секретам, immutable GameVersion, ratings nightly, restore-check,
честная маркировка NOT TESTED.

## Ограничения

Аудит был статическим (кроме JS 31/31); полный Python suite, PostgreSQL,
Docker, staging и browser E2E не воспроизводились внешней моделью. Для
production остаются обязательными: staging с реальным запасом RAM/swap,
полный Python gate, browser E2E, live session/score/leaderboard, ZIP
import/publish/rollback, beat/reapers/ratings, backup/restore.
