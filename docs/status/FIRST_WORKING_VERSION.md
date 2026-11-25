# Готовность первой рабочей версии — 2026-11-25

**Короткий вердикт:** dev/demo-контур готов к показу и ручной проверке
владельцем. Production-деплой и публикация обновлений уже опубликованных игр
пока **не готовы** — это owner-гейты, а не скрытые дефекты.

## Что проверено

- Полный Python gate: **1259 passed, 14 skipped, exit 0** (reuse-DB, 8:08,
  код на `ef242eb`; UX-шаблон входит в этот прогон).
- Browser E2E: **22 passed** (34–40 с), включая guest/auth submit, storage,
  leaderboard, restart, exit и возврат в каталог; Playwright Chromium.
- JS: **31/31**; ruff/format clean (485); mypy clean (393).
- Prod-style image (`INSTALL_DEV=false`): Playwright 1.65.1 и Chromium
  присутствуют, pytest отсутствует; сборка PASS.
- Browser publish gate: live positive 3/3 и negative page error; отдельный
  secretless-контейнер, web не исполняет игровой JS.
- ZIP Redis isolation: zip-worker не резолвит default broker/БД/кеш;
  dispatcher→cleanup и extraction доставлены live.
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
| CI browser E2E | job добавлен, локально 22/22; hosted run **NOT EXECUTED** | первый push/run и required check |
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

1. Дождаться первого hosted CI run и включить `e2e` в required checks.
2. Продуктовая приёмка владельцем dev/demo-сценариев.
3. Решить draft isolation §4.1 и PB `is_public`; после этого — UX-полировка
   и production deploy по owner-чеклисту.
