# Who's Undercover? — Pass & Play MVP report

**Дата:** 2026-11-26. **Версия:** 1.0.1. **Статус:** IMPLEMENTED /
CODE-REVIEW ACCEPT; product acceptance владельца остаётся.

## Что это

Новая игра Breaktime Arcade: социальная дедукция на одном устройстве для
4–12 игроков. Мирные знают одно слово, Undercover — близкое другое, Mr. White
не знает слова. Игроки по очереди дают подсказки, затем тайно голосуют.

## Реализованный объём

- Setup: 4–12 уникальных имён, 1–3 Undercover, опциональный Mr. White,
  10 колод слов, таймер, сохранение стола через SDK storage.
- Приватное раскрытие роли: отдельный handoff на каждого игрока, карта
  очищается до следующей передачи; на публичном снимке роли/слова скрыты.
- Раунд: ротация говорящих, подсказки, таймер, публичное поле и projector
  view, звуковые сигналы.
- Тайное голосование: передача устройства на каждого живого игрока, запрет
  self/dead/duplicate, ничья без выбывания.
- Победы: все чужие выбыли; чужих стало столько же, сколько мирных;
  пойманный Mr. White получает одну догадку и может украсть победу.
- Финал: раскрытие всех ролей и слов, история раундов, replay тем же столом
  и новый setup.
- Локали: en/ru UI и колоды; fallback en с бейджем покрытия платформы.
- Упаковка BA-GAME-2.2, каталог, обложка/2 скриншота, детерминированный ZIP.

## Проверки

- `node --test tests/js/whos_undercover.test.mjs` — 12 core tests.
- `npm run check:js` — syntax game/core/rng.
- Импорт ZIP через изолированный pipeline и publish — PASS (dev seed).
- `tests/e2e/test_whos_undercover_e2e.py` — полный раунд, privacy handoff,
  360 px, ru-локаль и projector; 3 E2E.
- Независимый code-review — ACCEPT; minors закрыты (html lang, touch target,
  aria-live, sanitize, category fallback, max session, undercover-win test).
- Полный Python gate — **1261 passed, 15 skipped, exit 0** (12:13).

## Осознанно вне объёма

**Live Room** (разные устройства, host/player/projector sync, reconnect)
требует нового платформенного room-контракта: комнаты, код входа, роли,
server-authoritative state, лимиты и TTL. BA-SDK-1.1 такого API не имеет, а
static game origin не может держать сервер. Pass & Play MVP не выдаётся за
Live Room; контракт-кандидат и этапы — в `PRODUCT_MASTER_ROADMAP.md`.

## Остатки

- Продуктовая приёмка владельцем, реальные плейтесты и баланс 4–12.
- 300+ пар слов, шесть языков или явная fallback-политика.
- Живой прод-деплой и CI-hosted run.
- Будущий room API и Live Room UX.
