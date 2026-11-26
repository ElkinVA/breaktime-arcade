# Готовность первой рабочей версии — 2026-11-26

**Короткий вердикт:** dev/demo-контур готов к показу и ручной проверке
владельцем. Production-деплой и публикация обновлений уже опубликованных игр
пока **не готовы** — это owner-гейты, а не скрытые дефекты.

## Что проверено

- Полный Python gate (LR-2b): **1291 passed, 17 skipped, exit 0
  (814 s)**; предыдущий checkpoint — 1261 passed, 15 skipped.
- Browser E2E: **25 passed** Pass & Play/portal + **3 passed** Live Room
  LR-2b (4–5 независимых contexts; civilian win/replay, true 2:2 tie,
  Mr. White steal); финальный current-source harness — **3 passed**;
  Playwright Chromium.
- Live Room LR-2b: `games-src/whos_undercover_live` 1.0.0, SDK `^1.2`,
  create/join/lobby/reveal/clues/vote/tie/Mr. White/final/replay,
  reconnect/stale; independent code+security review ACCEPT; hosted CI
  run #155 — success.
- CI Stage 1: `f89ece6`, GitHub Actions run #154 — success
  (quality/frontend/e2e/image/django-next).
- JS: **31/31 + 12/12 game core**; ruff/format clean (488); mypy clean (394).
- Prod-style image (`INSTALL_DEV=false`): Playwright 1.65.1 и Chromium
  присутствуют, pytest отсутствует; сборка PASS.
- Browser publish gate: live positive 3/3 и negative page error; отдельный
  secretless-контейнер, web не исполняет игровой JS.
- ZIP Redis isolation: zip-worker не резолвит default broker/БД/кеш;
  dispatcher→cleanup и extraction доставлены live.
- Who's Undercover? Pass & Play 1.0.1: 10 колод en/ru, privacy handoff,
  тайное голосование, все win-сценарии, replay, timer/sound/projector;
  ZIP импортирован/опубликован через pipeline; code-review ACCEPT.
- `./verify_stack.sh`: шесть обязательных сервисов healthy, HTTPS/статика
  отвечают.

## Что осознанно не готово

| Область | Состояние | Кто закрывает |
|---|---|---|
| Production nginx game hosts/TLS, `compose.prod.yml`, домены | пусто/не настроено | владелец: домены, TLS, deploy |
| Staging | остановлен из-за RAM; browser gate выключен до browser-testable topology | владелец: ресурсы/топология |
| Обновление published/hidden/archived игр | блокируется до draft isolation §4.1 | владелец: решение по схеме/приоритету |
| PB `is_public` семантика | не выбрана | владелец: продуктовое решение |
| Redis auth внутри `zipnet` | нет; граница — сеть | при необходимости отдельное решение |
| CI browser E2E | run #154 на `f89ece6` — success; run #155 на LR-2b commit `2c9d8f7` — **success** (включая e2e) | следующий CI run; required check |
| Live Room LR-3 | load/crash/observability, host-loss E2E, server create idempotency не реализованы | отдельный LR-3 пакет |
| UX | шапка плеера показывает название игры и переносится на мобильном; локализация ошибок старта и продуктовая restart-кнопка — остаток | отдельные UX-задачи |
| Юридические тексты, email-провайдер, права на игры | не выполнялись | владелец |

## Как проверить локально

```bash
make env
make certs
make build
make up
make probe-seed
make e2e
make test
./verify_stack.sh
```

Портал: https://portal.test:8443. E2E требует Chromium и hosts-запись
`portal.test`; в CI это уже автоматизировано.

## Следующий безопасный шаг

1. Hosted CI run #155 на LR-2b коммите подтверждён; включить `e2e` в
   required checks.
2. Продуктовая приёмка владельцем dev/demo-сценариев, включая Live Room
   forfeit/host-claim UX.
3. LR-3: load/crash/observability и host-loss E2E; затем draft isolation
   §4.1, PB `is_public` и production deploy по owner-чеклисту.
