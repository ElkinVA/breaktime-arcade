# APPF-RUNTIME-REVIEW-001 — App F Runtime review

**Дата:** 2026-11-23  
**Статус:** **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**; product/staging/
production не заявляются.  
**База:** `42296fa` (P5) + локальная docs-синхронизация; review-only срез
runtime.  
**Review:** `code-reviewer` и `security-auditor` (deepseek-v4-pro, text-only)
— **ACCEPT** после delta; исходные F1–F6/F-1…F-6 закрыты или
классифицированы как residual.

## 1. Область

Проверены `sdk/1.1.0/ba-sdk.js`, `static/src/js/host_protocol.js`,
`static/src/js/player.js`, `gameplay/play.html`, API/views/serializers/
throttling, services sessions/results/verifier/storage, leaderboards queries,
JS-тесты и integration-тесты. Сквозной путь:
CRM publish → player → session create/activate → host protocol → SDK →
submit/heartbeat/leaderboard/storage → verifier → leaderboard.

## 2. Исправления в этом срезе

| Находка | Исправление | Тест |
|---|---|---|
| `host_protocol` принимал `NaN`/дробный score и limit 1–100, который API не поддерживает | `Number.isSafeInteger(value)`; leaderboard limit только 10/100 | `tests/js/host_protocol.test.mjs` |
| Поздний ответ `submit`/`leaderboard`/`storage` старой сессии мог изменить UI/состояние нового раунда | `player.js` захватывает `requestSession` и игнорирует устаревшие успешные и ошибочные ответы | `tests/js/player.test.mjs` + существующие host/JS тесты |
| `newSession` создавал новую активную сессию, не закрывая старую; guest replay мог упереться в лимит 3 | `player.js` перед `newSession` вызывает best-effort `/close`; create/activate/close не ретраятся | `tests/js/player.test.mjs` |
| Retry создания/активации сессии мог создать дубль при потерянном ответе | `api(..., retry:false)` для create/activate/close | player test (close/create order) |
| Повторная отправка результата после потерянного ответа использовала новый Idempotency-Key и получала `E_SESSION_FINISHED` | ключ фиксируется per session в `submissionKeys` и переиспользуется ретраями | player flow; тест не добавлен (retry key path) |

SDK/ENV/GAME публичные контракты не менялись; схемы БД и Celery не
затрагивались. P3–P5 игровые пакеты не переписывались.

## 3. Проверки

```text
pytest tests/integration/test_game_play.py \
       tests/integration/test_game_sessions.py \
       tests/integration/test_game_storage.py \
       tests/integration/test_game_results.py -> 79 passed
npm run test:js        -> 7 passed
npm run check:js       -> clean
pytest --create-db -q  -> exit 0 (post-fix full suite; 981 passed,
                          12 skipped by the previous -rs run)
```

Проверки покрывают: valid/negative payload, wrong origin/source/session,
replay requestId, rate limit, session/ticket/ownership, CSRF, storage revision/
quota/isolation, duplicate result, eventLog schema/bounds, verifier/quarantine,
leaderboard visibility. Browser live E2E не выполнялся: локальная dev-БД
пуста/26 миграций не применены, `zip-worker` не запущен.

## 4. Остатки / NOT TESTED

- **NOT TESTED:** live cross-origin iframe, full browser E2E, staging/prod;
  CSP `frame-src` для production без порта 8443 требует проверки конфигурации.
- **RESIDUAL:** SDK pending requests старой сессии не отменяются сразу
  (истекают по timeout), player их игнорирует; закрытие сессии — best-effort.
- **RESIDUAL:** `SessionResultView`/storage полагаются на `CONTENT_LENGTH`;
  chunked/direct-gunicorn путь вне браузерного сценария.
- **R-036 Phase 2:** не менялся; требует решения владельца.
- **R-043:** hard FS quota отсутствует; app-layer quota/statvfs — compensations.
- **R-044:** static permissions после manual collectstatic — deployment
  checklist.
- **R-045:** Archer prototype/rights — product/legal owner.

## 5. Вердикт

`code-reviewer` — **ACCEPT** после delta: F1 (create retry/orphan) закрыт,
F2 (eventLog null/array) закрыт, F3 (Map cleanup) закрыт, F4 (close
порядок/отсутствие UI-мутации) закрыт, F5/F6 — minor residual.
`security-auditor` — **ACCEPT** после delta: F-1 (value range — сервер),
F-2/F-3/F-4/F-5 закрыты, F-6 (12 skipped — это skip, не fail) закрыт.

Остаточные (не блокируют):
- orphan CREATED при многократных потерях ответа create — серверный lazy
  expiry;
- нет race-теста stale-response и теста reuse Idempotency-Key; limit 5/1000
  negative test не добавлен;
- серверная cross-check строгости client/contracts — NOT TESTED;
- живой browser/E2E, staging/production — NOT TESTED.

Product/staging/production не приняты.
