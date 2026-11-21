# BA-APPF-002 / App F runtime, SDK and player — срез A+B

**Дата:** 2026-11-21
**Статус:** **IMPLEMENTED / TECHNICAL REVIEW**. Контракты BA-SDK-1.1
v1.1.0 submitted, но не утверждены владельцем; продуктовая приёмка не
заявляется.

## 1. Границы среза

Реализован вертикальный срез A+B:

- официальный `sdk/1.1.0/ba-sdk.js`;
- host-протокол `static/src/js/host_protocol.js`;
- host-страница `static/src/js/player.js` + `gameplay/play.html`;
- `game_play` view с серверным созданием/активацией сессии;
- runtime URL из `GameVersion.host_label` + `runtime_hash` (full 64 hex);
- тесты view/SDK-контракта и JS syntax checks.

Входит также test-only probe (`games-src/probe`) и Playwright E2E handshake.
Не входит: staging/prod runtime origin, EventLog/verifier/replay, CRM
preview/autotest flow.

## 2. SDK

`sdk/1.1.0/ba-sdk.js` — classic IIFE, CSP-safe, без cookies/localStorage/
indexedDB/top.location/parent.document.

- fragment `#p=<portal_origin>&s=<session_uuid>`, https + UUID validation;
- `BreaktimeArcade.init({timeoutMs})` — 5 с, `ba:hello`, ожидание
  `ba:context`;
- проверки: `source=parent`, exact parentOrigin, envelope/source/protocol,
  host allowlist, sessionId, UUID requestId, LRU 512, 60/мин;
- API: `context`, `ready`, `t`, `on`, `submitResult` (10 с, guest
  normalization), `leaderboard.top(10/100)`, `leaderboard.myBest`,
  `storage.get/set/remove`, `newSession`, `exit`, `fail`;
- ticket в SDK/iframe не передаётся.

## 3. Host и player

`HostBridge` проверяет `event.source === iframe.contentWindow`, точный
`iframeOrigin`, envelope/source/protocol/type, sessionId, requestId UUID/LRU,
60/мин, state и payload limits; отправляет только на exact targetOrigin.

`player.js` держит публичный context на host, релеит:

- submit → `POST /api/v1/sessions/{id}/result` с `Idempotency-Key`;
- leaderboard → `/leaderboard` и `/me/best`;
- storage → `GET/PUT /api/v1/games/{id}/storage` с ETag/If-Match и
  key-level API поверх единого JSONB;
- newSession → `POST /sessions` + `/activate`;
- exit → `/close`;
- pause/resume по visibility;
- CSRF через `X-CSRFToken`.

`game_play` view:

- серверно `create_session` + `activate_session`; ticket не рендерится;
- `Cache-Control: no-store`;
- guest cookie пробрасывается в request до активации;
- те же subject/IP throttle, что API сессий;
- runtime URL: `https://<host_label>.<GAMES_DOMAIN>:<portal_port>/v/<runtime_hash>/index.html#p=...&s=...`;
- `play.html`: iframe sandbox `allow-scripts allow-same-origin`, context в
  data-атрибуте, ticket отсутствует;
- `game_detail` получил Play link.

nginx dev `/v/<vhash>` расширен до 12–64 hex.

## 4. Проверки

```text
play/SDK targeted -> 7 passed
pytest (full)     -> 448 passed, 4 skipped, 1 warning
runtime E2E       -> 1 passed (probe handshake + storage relay)
ruff/format/mypy  -> clean
npm run check:js  -> clean (3 files)
```

## 5. Независимый review

- code-reviewer — **INCOMPLETE** (text-only без diff): session binding,
  storage namespacing, camelCase mapping, sandbox origin, Idempotency-Key
  source требуют подтверждения кодом/E2E.
- security-auditor — **INCOMPLETE**: parentOrigin из fragment
  attacker-influenceable; нужен build-time pin (добавлена поддержка
  `window.BA_PORTAL_ORIGIN` с проверкой fragment), E2E/probe, server-side
  guest rejection и JSON-Schema validation evidence. Статус не accepted.

## 6. Остатки

- Probe/E2E есть; staging/prod runtime volume/origin ещё не настроены.
- JS payload validation — lightweight, не полный JSON Schema 2020-12.
- API `POST /sessions` по-прежнему отдаёт snake_case `session_id`, SDK/host
  context — camelCase `sessionId`; нужен adapter/contract decision.
- `ba.t` без строки возвращает key (нужен fallback/политика).
- SDK не делает retry-loop; host fetch не ретраит.
- Runtime origin для staging/prod не настроен; dev — `*.games.test:8443`.
- BA-SDK-1.1/BA-ENV-1.1/BA-GAME-2.2 не утверждены; статус только
  IMPLEMENTED/TECHNICAL REVIEW.
