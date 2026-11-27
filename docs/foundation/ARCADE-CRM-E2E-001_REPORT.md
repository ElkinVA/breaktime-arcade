# ARCADE-CRM-E2E-001 — CRM staff browser E2E

**Дата:** 2026-11-27
**Статус:** COMPLETED / QA PASS / REVIEWER ACCEPT; product acceptance owner.
**Commit:** `0eca6a0` (`test(e2e): add CRM staff browser scenarios`).

## Результат

Добавлен host Playwright suite `tests/e2e/test_crm_e2e.py`:

- staff login с TOTP 2FA;
- CRM dashboard с текущим staff и счётчиками;
- games list, game card и version history;
- step-up с одноразовым TOTP;
- разрешение seeded complaint с resolution note;
- audit log visibility.

Fixture создаёт одноразового owner staff, игру/версию и жалобу в dev DB
через `manage.py shell`; используется локальный dev-lite стек, не production.
Без `BA_E2E=1` модуль пропускается на collection; skip не маскирует failure.

## Проверки

- Host CRM E2E: **2 passed**; повторный прогон — **2 passed**.
- `make lint`: clean, **516 files formatted**.
- `make types`: **412 source files**, clean.
- Standard suite: **1366 passed, 17 skipped, exit 0** (prior clean run; this
  commit adds an opt-in E2E module).
- Full local `make e2e`: **31 passed, 1 failed**; единственный failure —
  unrelated LR-3 host-loss из-за устаревшего published runtime и
  `V_PUBLISHED_UPDATE_BLOCKED`. Не skip/маска.

## QA / Reviewer

- QA: **PASS**; acceptance 1–3 подтверждены, skip masking отсутствует.
- Reviewer: **ACCEPT** после отзыва ошибочного PEP 758 blocker (Python 3.14
  разрешает `except A, B:` без скобок). Minor residuals: dev fixture
  accumulation, слабый dashboard assertion, deprecated
  `expect_navigation`, реестры обновляются после приёмки.

## Evidence

- `.autonomy/evidence/crm-e2e-001-evidence-2026-11-27.json`
- `.autonomy/evidence/qa-independent-crm-e2e-001-2026-11-27.json`
- `.autonomy/evidence/reviewer-independent-crm-e2e-001-2026-11-27.json`
- `.autonomy/evidence/crm-e2e-001-integration-evidence-2026-11-27.json`

## Остатки

- Fixture оставляет dev-only owner users/game/version/complaint/audit rows;
  cleanup не реализован.
- Full `make e2e` остаётся red из-за unrelated LR-3 stale runtime.
- PEP 758 syntax требует Python >=3.14; стек закреплён на 3.14.
- `page.expect_navigation()` deprecated; заменить при обновлении Playwright.
