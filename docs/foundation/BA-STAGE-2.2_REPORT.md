# BA-STAGE-2.2 — 2FA персонала

**Дата:** 2026-11-19  
**Статус:** **PARTIAL** — TOTP-2FA, recovery-коды, двухшаговый вход,
disable и staff-middleware реализованы и проверены в dev. Офлайн-код
восстановления владельца, отдельный журнал входов/SecurityEvent, роли/CRM
step-up и browser E2E не реализованы. Это self-check исполнителя, не
независимый аудит и не приёмка §2.20.

## 1. Нормативная база

§2.20 BA-PLAT-4.2: обязательный TOTP 2FA для служебных аккаунтов, лимит
входа, журнал, 10 одноразовых recovery-кодов, step-up для чувствительных
CRM-действий, уведомления о смене 2FA/email/ролей. CRM и роли в текущем
каркасе отсутствуют, поэтому step-up/роли не реализовывались. Staging и
production не затрагивались.

## 2. Что реализовано

- `User.totp_secret` (base32), `User.totp_last_counter`; существующее
  `totp_confirmed_at`.
- `RecoveryCode`: 10 кодов, SHA-256 hash, `used_at`, unique на пользователя.
- `apps/accounts/services/two_factor.py`:
  - генерация секрета и provisioning URI;
  - TOTP-проверка с окном ±1 шаг;
  - replay-protection по counter;
  - генерация/проверка одноразовых recovery-кодов;
  - enable/disable.
- Двухшаговый вход staff: пароль → `/auth/2fa/` (TOTP) или
  `/auth/2fa/recovery/`; до второго фактора `auth_login` не выполняется.
- Первый вход staff без 2FA → `/auth/2fa/setup/`; после подтверждения кода
  показываются 10 recovery-кодов, затем вход завершается.
- `/auth/2fa/disable/`: password + TOTP, инвалидация прочих сессий,
  logout.
- `StaffTwoFactorMiddleware`: staff-сессия без `totp_confirmed_at`
  направляется на setup; сессия без `ba_2fa_verified` завершается.
- Уведомление на verified email при enable/disable; структурированные
  логи `account.2fa.enabled/disabled/recovery_used`.
- Миграция `accounts.0003_user_totp_last_counter_user_totp_secret_recoverycode`
  применена в dev.

## 3. Файлы

- `apps/accounts/models/user.py`, `models/security.py`, `models/__init__.py`
- `apps/accounts/services/two_factor.py`, `services/rate_limit.py`,
  `services/email.py`
- `apps/accounts/forms.py`, `views.py`, `urls.py`, `middleware.py`
- `apps/accounts/templates/accounts/two_factor_*.html`,
  `accounts/profile.html`
- `config/settings/base.py`
- `apps/accounts/migrations/0003_*.py`
- `tests/integration/test_two_factor.py`

## 4. Фактические проверки

```text
python -m pytest
173 passed, 1 skipped in 34.54s

python -m ruff check apps config tests
All checks passed!

python -m ruff format --check apps config tests
326 files already formatted

python -m mypy
Success: no issues found in 312 source files

python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected

python manage.py migrate --plan
No planned migration operations.
```

6 integration tests: setup → TOTP login; replay rejection; recovery code
single-use; disable with password+TOTP; middleware rejection of a staff
session without the verified flag; non-staff login unchanged.

## 5. Security-свойства

- TOTP mandatory для staff; пароль без второго фактора не создаёт
  authenticated session.
- Replay одного TOTP-кода отклоняется.
- Recovery-коды одноразовые, в БД только hash.
- Disable требует password+TOTP и завершает прочие сессии.
- Staff-middleware не пропускает сессию без verified-флага.
- Email-уведомление при изменении 2FA.
- 2FA-попытки ограничены по аккаунту и IP (fail-open при отказе cache —
  R-019).

## 6. Не реализовано / блокеры

| Требование §2.20 | Состояние |
|---|---|
| TOTP для служебных аккаунтов | Реализовано для `is_staff` |
| 10 recovery-кодов | Реализовано |
| Офлайн-код восстановления владельца | Не реализовано; нужен процесс владельца |
| Журнал входов/SecurityEvent в БД | Только structured logs; модель не реализована |
| Роли и step-up для CRM | CRM/роли отсутствуют |
| Уведомления о смене ролей | Ролей нет; 2FA/email уведомления есть |
| Browser E2E 2FA | Не реализовано |
| Шифрование TOTP-секрета | Секрет хранится base32 в БД (R-020) |

## 7. Следующий шаг

`BA-STAGE-2.3`: browser E2E регистрации/входа/2FA и закрытие доступных
account-пробелов. Офлайн-recovery, журнал/SecurityEvent и CRM step-up
требуют решения владельца/CRM и не должны изобретаться исполнителем.
