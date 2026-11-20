# APPF-SESSION-002 — throttle hardening: identity + IP, heartbeat per session

**Дата:** 2026-11-20  
**Статус:** PLAN (implementation after APPF-SESSION-001 acceptance)  
**Основание:** OD-APPF-020…026 (мульти-identity требует защиты);
BA-PLAT-4.2 Приложение E; §2.20 (NAT, challenge); security-review F-1/F-6;
R-030; `docs/decisions/THROTTLE_REDIS_DECISION.md`.

## Цель

Привести лимиты к Приложению E и закрыть амплификацию через создание
множества гостевых identity, не блокируя корпоративный NAT.

## Нормативная база (Приложение E)

| Операция | Первичный ключ | Вторичный IP | Реакция |
|---|---|---|---|
| Создание сессий | 30/час на субъект | 600/час на IP (/64) | challenge после IP-порога |
| Heartbeat | 3/мин **на сессию** | — | 429 |
| Результаты (future) | 60/час субъект | 1200/час IP | 429 + журнал |

ТЗ требует **прогрессивный challenge**, а не жёсткую блокировку NAT. Пока
challenge (PoW/CAPTCHA, ЕС) не реализован, вторичный IP-лимит временно
возвращает 429 `E_RATE_LIMIT`; это осознанно более строгая мера, помеченная
`[PROP]` до появления challenge. Порог 600/час выбран из ТЗ.

## Решение

1. **Создание сессий:** `SubjectScopedRateThrottle` (30/час) — ключ user или
   живая identity; без валидной identity — IP. Дополнительно
   `GuestIpRateThrottle` (600/час) только для анонимных запросов; ключ IP
   (IPv6 — /64). Аутентифицированные пользователи IP-лимитом не режутся.
2. **Heartbeat:** отдельный `SessionScopedRateThrottle` (3/мин) с ключом
   `session_id` из URL (ТЗ: на сессию, не на субъект). Отсутствие session_id —
   deny.
3. **429:** структурированный `{code:"E_RATE_LIMIT", message:"Too many
   requests"}` через DRF exception handler для `Throttled`; `Retry-After`
   сохраняется. Локализация — по коду на клиенте.
4. **Redis:** alias `throttle` (noeviction, отдельный инстанс) по
   `THROTTLE_REDIS_DECISION.md`; throttle-классы используют его; отказ
   backend — fail-open с ERROR-логом (публичные игры не ломаются).
5. **Обоснование лимитов:** subject 30/час — из ТЗ; IP 600/час — из ТЗ
   (20× субъектного), допускает ~20 новых гостевых identity/час с одного IP
   и ~10 созданий/мин в NAT; после challenge порог можно сохранить, добавив
   прогрессивную проверку вместо 429.

## Acceptance criteria

- 2+ разных валидных identity с одного IP: после исчерпания IP-бакета
  создание → 429, несмотря на свежие subject-бакеты.
- Один субъект: 31-е создание за час → 429 (subject).
- Аутентифицированный пользователь при исчерпанном IP-бакете → создание
  разрешено (subject-лимит).
- Heartbeat: 4-й запрос за минуту в одну сессию → 429; heartbeat в другую
  сессию того же субъекта не блокируется (per-session).
- 429 тело — `{code:"E_RATE_LIMIT", message}`; `Retry-After` присутствует.
- Отказ throttle-кэша → запрос обрабатывается (fail-open), ERROR-лог.
- Все прежние 24 теста APPF-SESSION-001 и полный suite зелёные; lint/types/
  migrations.

## Файлы

`config/settings/base.py` (alias throttle, exception handler),
`apps/gameplay/api/throttling.py`, `apps/gameplay/api/views.py`,
`config/urls.py` (без изменений), `compose.dev-lite.yml` (+ staging при
наличии), `.env.example`, тесты `tests/integration/test_game_sessions.py` /
новый модуль throttle.

## Stop conditions

- Нет данных о NAT-нагрузке → порог 600/час остаётся [PROP] из ТЗ, не
  снижается самовольно.
- Challenge не реализуется в этом пакете; 429 — временная мера, отметить в
  отчёте и NOW.
- Не менять ТЗ; не добавлять сторонние сервисы challenge без решения
  владельца (финансы/юрисдикция).
