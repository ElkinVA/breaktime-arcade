# APPF-POPULARITY-001 — зачёт популярности и дневная статистика

**Дата:** 2026-11-20  
**Статус:** IMPLEMENTED / AWAITING OWNER ACCEPTANCE; independent review —
`code-reviewer` и `security-auditor`: **accept**, блокеров нет (guest
identity inflation — owner-gap).  
**Основание:** BA-PLAT-4.2 §2.8, §2.22; Приложение D.

## 1. Реализация

`GamePlayCredit` (game, subject_type, subject_id, last_credited_at;
UNIQUE) и `GameDailyStats` (game+date unique; sessions, unique_sessions,
completions, avg_duration_ms). Зачёт при завершении сессии
(`finished`/`aborted`/`expired`) при длительности ≥15 с и
`mode ∈ {user, guest}`; preview/autotest исключены. SQL upsert обновляет
`last_credited_at` только если прошло ≥30 минут; только фактический зачёт
инкрементит `unique_sessions` за текущую дату UTC. `sessions` растёт на
каждое завершение, `completions` — на результат, `avg_duration_ms`
пересчитывается инкрементально.

Вызовы: heartbeat при переходе в `expired`, `submit_result` после
`finished`, `close_session` при `active`. `POST /sessions/{id}/close`
(CSRF, ownership, idempotent 204) переводит active в `aborted` с зачётом,
созданную — в `aborted` без зачёта.

## 2. Проверки

```text
pytest tests/integration/test_game_popularity.py -> 8 passed
pytest (full) -> 281 passed, 2 skipped
make lint -> All checks passed
make types -> Success: 320 source files
makemigrations --check -> No changes detected
```

Тесты: user close 204/aborted/credit/stats + идемпотентный повтор; guest
close кредитует anon, preview исключён; <15 с не кредитует; окно 30 минут
(sessions=3, unique=2, completions=1, avg=30 000); ровно 15 с кредитуется;
ownership close → 403; created → aborted без кредита; expired heartbeat
кредитует server duration; UTC-границы дат; параллельные close двух сессий
одного субъекта → один unique; завершение result кредитует `credited_ms`
(серверная длительность), а не клиентский `duration_ms`.

## 3. Остаточные риски

- Ротация guest identity даёт новый зачёт (как и в throttle): потолок
  ограничен капами создания identity (~60 зачётов/ч на IP), но популярность
  можно накрутить скриптом. §2.8 IP-флор не задаёт — **owner-gap R-032**
  (IP-окно или пониженный вес гостевых зачётов — решение владельца).
- `sessions`/`completions`/`avg_duration` семантика — минимально необходимая
  для §2.8; расширение (уникальные по дням, распределения) — по CRM.
- Агрегат популярности (сумма за 30 дней, Redis-кеш 15 мин) пока не
  реализован как read-endpoint; данные для него есть.
- `close` для `created` переводит в `aborted` без зачёта — [PROP],
  зафиксировать в контракте SDK.
