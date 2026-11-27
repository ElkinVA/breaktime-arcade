# ARCADE-EMAIL-RESET-RACE-001 — submission-order race

**Дата:** 2026-11-27
**Статус:** COMPLETED / CODE REVIEW ACCEPT / SECURITY REVIEW ACCEPT /
SANDBOX FULL SUITE GREEN / product acceptance owner.
**Коммиты:** `401df05` (candidate), `11ea832` (test setup fix), `71177d2`
(sandbox config fix).

## Результат

`_update_email` и POST-ветка `password_reset_confirm` берут один и тот же
`User.objects.select_for_update()` до чтения `EmailAddress` и до
потребления reset-токена. Обе операции сериализуются:

- если email change/removal зафиксирован первым, старый reset-токен уже
  инвалидирован и не может сменить пароль;
- если reset захватил lock первым, он завершается против всё ещё
  актуального verified-адреса, после чего применяется email change/removal.

`send_email_change_notice` получает старый адрес строкой, вызывается после
коммита и не удерживает транзакцию на время отправки письма. Схема и
migrations не менялись.

## Тесты и проверки

- `tests/integration/test_accounts_email_reset_race.py`: **4 passed** (два
  порядка × change/removal), PostgreSQL-only.
- Полный sandbox suite: **1359 passed, 11 skipped, exit 0** (1370 collected).
- Sandbox ruff: `All checks passed!`, **515 files formatted**.
- Sandbox mypy: `Success: no issues found in 412 source files`.
- `make lint` + `make types` на main после merge: clean.
- Code review: **ACCEPT**, без must-fix; отмечены minor: удержание User
  lock на `set_password`/session invalidation, токен сжигается до проверки
  адреса, редкая ложноположительная проверка `blocked` в тесте при
  медленном старте потока.
- Security review: **ACCEPT**, без must-fix. Отмечены minor/pre-existing:
  reset-request читает адрес без lock (confirm перепроверяет адрес),
  AB-BA с `verify_email_token` (pre-existing, вне scope), отсутствие
  письма при удалении адреса (parity с прежним поведением).

## Почему первые два запуска были заблокированы

Это была ошибка trusted sandbox, а не кандидата: sandbox не копировал
`ruff.toml`/`mypy.ini` и запускал ruff по всему дереву, включая
`.claude/hooks`. Подробности и исправление — `AUTONOMY_SANDBOX_CHECKS_FIX.md`.

## Остаточные риски

- Пароль хешируется и другие сессии инвалидируются, пока удерживается
  User lock; это влияет только на того же пользователя и требует валидного
  одноразового токена.
- Reset-request может выпустить письмо на адрес, который меняется
  конкурентно; confirm отклоняет и сжигает такой токен.
- Pre-existing AB-BA между `verify_email_token` и `_update_email` требует
  отдельного follow-up с User lock в verify-пути.
- Browser E2E/продуктовая приёмка не выполнялись; это вне scope и остаётся
  за владельцем.
