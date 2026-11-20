# BA-STAGE-2.4 — 2FA completion

**Дата:** 2026-11-19  
**Статус:** **PARTIAL** — owner offline recovery, журнал входов
(`LoginEvent`) и regeneration recovery-кодов реализованы и проверены.
Роли/CRM step-up, уведомления о смене ролей, шифрование TOTP-секрета и
retention cleanup остаются. Это self-check, не независимый аудит и не
приёмка §2.20.

## 1. Реализовано

- `OwnerRecoveryCode`: офлайн-код только для `is_superuser`, one-time,
  SHA-256 hash; выдаётся при setup/regeneration; после использования
  2FA сбрасывается и требуется повторный enrollment.
- `LoginEvent`: login_failed/login_success/password_ok/2fa_success/
  2fa_failed/recovery_used/owner_recovery_used/2fa_enabled/2fa_disabled;
  хранится hash subject/IP, без plaintext login/IP.
- `/auth/2fa/owner-recovery/`: восстановление владельца → обязательный
  setup.
- `/auth/2fa/regenerate/`: password + TOTP → новые 10 recovery-кодов;
  для superuser — новый owner code.
- События enable/disable/recovery пишутся в `LoginEvent` и structured
  logs; email-уведомление при enable/disable уже было в 2.2.
- Миграция `accounts.0004_ownerrecoverycode_loginevent` применена в dev.

## 2. Фактические проверки

```text
python -m pytest
176 passed, 2 skipped in 31.85s

python -m ruff check apps config tests
All checks passed!

python -m ruff format --check apps config tests
328 files already formatted

python -m mypy
Success: no issues found in 313 source files

python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected

python manage.py migrate --plan
No planned migration operations.
```

9 2FA integration tests, включая owner recovery, regeneration, single-use
recovery, replay rejection, disable, middleware и journal без plaintext.

## 3. Не реализовано

| Требование | Состояние |
|---|---|
| Роли и CRM step-up | CRM/роли отсутствуют; пакет не может их закрыть |
| Уведомления о смене ролей | Ролей нет |
| Шифрование TOTP-секрета | Секрет хранится base32 (R-020) |
| Retention `LoginEvent` 12 мес. | Не реализован; вынесен в BA-STAGE-2.5 |
| Browser E2E staff 2FA | Не добавлен; integration tests покрывают сценарии |

## 4. Следующий шаг

`BA-STAGE-2.5`: retention cleanup для `LoginEvent`, `AnonymousIdentity`,
`AccountToken`, `NicknameReservation` и связанных сроков; Celery Beat.
