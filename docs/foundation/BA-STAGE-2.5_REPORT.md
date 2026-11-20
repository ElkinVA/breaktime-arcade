# BA-STAGE-2.5 — account retention cleanup

**Дата:** 2026-11-19  
**Статус:** **PARTIAL** — аккаунтные сроки §2.22 реализованы; глобальные
`SecurityEvent`/игровые/mail/backup/consent сроки не покрыты. Self-check,
не независимый аудит и не приёмка.

## 1. Реализовано

Celery Beat `accounts.cleanup_expired_account_records` (ежедневно):

- `AnonymousIdentity` с `expires_at < now`;
- `AccountToken` с `expires_at < now`;
- `LoginEvent` старше `LOGIN_EVENT_RETENTION_DAYS` (365);
- `NicknameReservation` с `reserved_until < now`.

`NICKNAME_RESERVATION_DAYS=730` используется при анонимизации аккаунта.
Задача возвращает counts по каждой категории для мониторинга.

## 2. Фактические проверки

```text
python -m pytest
177 passed, 2 skipped in 54.83s

python -m ruff check apps config tests
All checks passed!

python -m ruff format --check apps config tests
329 files already formatted

python -m mypy
Success: no issues found in 313 source files

python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected

python manage.py migrate --plan
No planned migration operations.
```

1 integration test проверяет удаление только истёкших/старых записей и
сохранение будущих/свежих.

## 3. Не покрыто

| Срок §2.22 | Состояние |
|---|---|
| `AnonymousIdentity` 90 дней | Реализовано через `expires_at` |
| `SecurityEvent` 12 мес. | Модель App F отсутствует; `LoginEvent` 365 дней — частичная замена |
| Сырые события 90 дней, `GameSession` 30 дней, `GameStorage` 90 дней | Модели App F отсутствуют |
| Почтовые логи 30 дней | Провайдер/логи не реализованы |
| Бэкапы 30 дней | CRM backup retention есть отдельно; не в этой задаче |
| Согласия «срок + 12 мес.» | Не реализовано |
| `GameImportDraft`/`GamePlayCredit` | App F отсутствует |

## 4. Следующий шаг

`BA-QUALITY-001`: coverage доменных модулей ≥70 %, CI-порог и анализ
пробелов.
