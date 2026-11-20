# APPF-SESSION-002 — throttle hardening report

**Дата:** 2026-11-20  
**Статус:** IMPLEMENTED / AWAITING OWNER ACCEPTANCE; independent review —
`code-reviewer` и `security-auditor` (deepseek-v4-pro, text-only):
**блокеров нет**.  
**План:** `docs/tasks/APPF-SESSION-002_PLAN.md`  
**Основание:** OD-APPF-020…026; BA-PLAT-4.2 Приложение E; R-030.

## 1. Итог

Throttle приведён к Приложению E: создание сессий — 30/час на субъект +
600/час на IP (/64), heartbeat — 3/мин на сессию; structured 429; отдельный
`redis-throttle` (noeviction) для предсказуемых счётчиков; реальный
клиентский IP доставляется из nginx. Мульти-identity обход закрыт: ротация
identity не создаёт свежих subject-бакетов без IP-бакета.

## 2. Лимиты и ключи

| Операция | Лимит | Ключ | Источник |
|---|---|---|---|
| Создание сессий (subject) | 30/час | `user:<id>` / `anon:<identity>` / `nosubject:<ip>` | §2.12, Прил. E |
| Создание сессий (IP, анонимные) | 600/час | `ip:<addr/64>` | Прил. E |
| Heartbeat | 3/мин | `(<subject>, <session_id>)` | Прил. E |
| Результаты | 60/час | subject | Прил. E |

Аутентифицированные не режутся IP-лимитом (NAT). IPv4-mapped IPv6
нормализуется к IPv4; обычный IPv6 агрегируется по /64.

## 3. Реальный IP

`ClientIPMiddleware` принимает `X-Forwarded-For` только если `REMOTE_ADDR`
входит в `BA_TRUSTED_PROXY_NETWORKS` (env `TRUSTED_PROXY_IPS`, default —
localhost + private), и берёт последний элемент. nginx dev переписывает
заголовок (`$remote_addr`), staging append-схема даёт последний доверенный
адрес. Проверено на стеке: запросы через nginx из web и worker дали разные
IP-бакеты (172.19.0.3 / 172.19.0.5) вместо общего nginx-IP (172.19.0.6).
Staging smoke — pre-prod чек-лист. `TRUSTED_PROXY_IPS` не должен быть `*`;
для staging/prod — явные адреса прокси.

## 4. Redis

Отдельный сервис `redis-throttle` (redis:8-alpine по digest, noeviction,
без AOF/снапшотов, 64 МБ dev / 128 МБ base, healthcheck, internal network),
Django alias `throttle`, `REDIS_THROTTLE_URL`. При отказе backend throttle
fail-open с ERROR-логом не чаще 1/мин; решение и стоимость —
`docs/decisions/THROTTLE_REDIS_DECISION.md`.

## 5. Изменения

- `apps/gameplay/api/throttling.py` — subject/IP/session throttles,
  namespace-ключи, /64, fail-open.
- `apps/core/middleware.py` — ClientIPMiddleware.
- `apps/core/exceptions.py` — structured 429 (`E_RATE_LIMIT`, Retry-After).
- `config/settings/base.py` — alias throttle, rates `sessions_ip`,
  exception handler, trusted proxy networks.
- `apps/gameplay/api/views.py` — GuestIp на create, SessionScoped на
  heartbeat.
- `compose.yml`, `compose.dev-lite.yml`, `.env.example`,
  `infra/nginx/dev.conf` — redis-throttle, digest, XFF overwrite.
- Тесты: +12 (HTTP heartbeat, per-session throttle, IP cap, exempt user,
  max-duration boundary, repeat activation, PROTECT, fail-open, IPv6 /64,
  IPv4-mapped, key namespaces, rates, middleware).

## 6. Проверки

```text
pytest tests/integration/test_game_sessions.py -> 37 passed
pytest (full) -> 241+ passed, 2 skipped
make lint -> All checks passed
make types -> Success: 317 source files
stack: redis-throttle healthy; IP-бакеты различаются по клиентам
```

## 7. Review

- `code-reviewer`: блокеры SESSION-002 сняты (namespace, IPv4-mapped,
  middleware, digest); оговорки — staging smoke и узкий `TRUSTED_PROXY_IPS`.
- `security-auditor`: F-1/F-2/F-3 сняты; staging smoke — остаточный
  pre-prod чек-лист; `TRUSTED_PROXY_IPS` не делать широким.

## 8. Остаточные риски

- Challenge после IP-порога не реализован (O4): до его появления — 429;
  потолок амплификации с одного IP — 600 create/час (по ТЗ), затем challenge.
- Fail-open: при отказе redis-throttle лимиты отключены; алерт — infra.
- Рестарт redis-throttle обнуляет счётчики.
- NAT: 600/час на IP — компромисс; при жалобах сузить/расширить по данным.
- staging XFF smoke и явный `TRUSTED_PROXY_IPS` — до production.
