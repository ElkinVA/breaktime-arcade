# APPF-RUNTIME-REVIEW-001 — delta: stale-response and idempotency tests

**Дата:** 2026-11-23  
**Статус:** **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT** (code-reviewer ACCEPT
после исправления ложно-положительных deferred-ответов).  
**Основа:** `docs/foundation/APPF-RUNTIME-REVIEW-001_REPORT.md`,
`docs/tasks/APPF-RUNTIME-REVIEW-001_PLAN.md`.

## 1. Что добавлено

Новый изолированный test-file `tests/js/player_race.test.mjs` (production
код не менялся) покрывает остатки предыдущего review:

- stale success submit старой сессии после `newSession` не постится в новый
  раунд (`ba:result` отсутствует);
- stale error submit старой сессии не постится (`ba:error` отсутствует);
- stale leaderboard data и stale storage data старой сессии не постятся;
- два submit в одной сессии переиспользуют один `Idempotency-Key`;
- submit в новой сессии получает новый ключ (и ключ присутствует).

Deferred-ответы обёрнуты в Response-shaped helper (`ok/status/headers/json`),
поэтому `api()` действительно доходит до success-веток и guard'ов
`sessionId !== requestSession`; при удалении любого guard'а соответствующий
post появляется и тест падает.

## 2. Проверки

```text
npm run test:js  -> 8 node:test entries, 0 failed
                    (5 host_protocol + 1 player + 1 player_race + archer file entry)
npm run check:js -> clean
pytest tests/integration/test_migrations_check.py -> 1 passed
```

Python full suite не изменялся этим JS-only delta; предыдущий прогон —
1019 tests, 1011 passed, 8 skipped, exit 0.

## 3. Review

`code-reviewer` (deepseek-v4-pro) — первый проход **REJECT**: success
deferreds резолвились raw payload, поэтому submit/leaderboard/storage
success-guard'ы не достигались (assertions были vacuous). После замены на
`response(200, payload)` и добавления проверки наличия нового ключа —
**ACCEPT**: все четыре stale-потока падают при удалении guard'а, same-session
reuse и freshness key проверены невакуумно; изоляция файла и отсутствие
production-изменений подтверждены.

## 4. Остатки

- Live browser E2E/staging/production не запускались (dev-БД/миграции,
  внешние условия); это не приёмка.
- Серверная cross-check строгость client/contracts остаётся NOT TESTED;
  существующие verifier/result tests не менялись.
- `tests/integration/test_migrations_check.py` добавлен как постоянный guard
  для `makemigrations --check` (не входит в JS delta, но подтверждён).
