# ARCADE-ACCOUNTS-E2E-002 — account browser scenarios

**Дата:** 2026-11-27
**Статус:** COMPLETED / QA PASS / REVIEWER ACCEPT; product acceptance owner.
**Commit:** `5442127` (`test(e2e): extend account browser scenarios and stabilize leaderboard check`).

## Результат

Добавлены Playwright-сценарии на host runner:

- скачивание account export и проверка JSON;
- смена пароля и повторный вход с новым паролем;
- deletion request и cancel с проверкой видимого состояния;
- staff 2FA: enrollment, обязательная проверка при следующем входе, verify,
  disable и вход без повторной 2FA.

В тестовом окружении staff-пользователь создаётся через test-only fixture в
dev-lite БД (без email); TOTP генерируется `pyotp`. Продуктовый код не
менялся.

## Проверки

- Accounts E2E: **5 passed**.
- Базовые shell/account сценарии: **13 passed**.
- Полный стандартный suite: **1366 passed, 17 skipped, exit 0**.
- `make lint`: clean, **515 files formatted**; `make mypy`: **412 files**.
- `make e2e` целиком: **31 passed, 1 failed**. Единственный failure —
  `test_live_rooms_e2e.py::test_host_loss_requires_the_real_120_second_window`:
  опубликованный `whos_undercover_live` runtime не содержит `#claim-host`,
  а `make undercover-live-seed` отклоняется `V_VERSION_DUP` /
  `V_PUBLISHED_UPDATE_BLOCKED`. Это более поздний LR-3 сценарий вне
  baseline 13; он не пропускался и не маскировался.

## Evidence

- `.autonomy/evidence/accounts-e2e-002-evidence-2026-11-27.json`
- `.autonomy/evidence/qa-independent-accounts-e2e-002-2026-11-27.json`
- `.autonomy/evidence/reviewer-independent-accounts-e2e-002-2026-11-27.json`
- `.autonomy/evidence/accounts-e2e-002-integration-evidence-2026-11-27.json`

## Остатки

- Для полного зелёного `make e2e` нужен отдельный follow-up: обновить
  опубликованный dev runtime Live Room или использовать свежую disposable
  БД с повторным seed; published-update policy не обходилась.
- E2E создаёт dev-пользователей и staff с фиксированным тестовым паролем,
  без автоматического cleanup (dev-only).
- Повторные прогоны расходуют registration IP throttle; перед прогоном
  использовался test-only reset Redis throttle.
