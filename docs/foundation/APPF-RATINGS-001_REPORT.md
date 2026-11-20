# APPF-RATINGS-001 — оценки игр

**Дата:** 2026-11-20  
**Статус:** IMPLEMENTED / AWAITING OWNER ACCEPTANCE; independent review —
`code-reviewer` и `security-auditor`: **accept**, блокеров нет.  
**Основание:** BA-PLAT-4.2 §2.9, §2.23; Приложение E.

## 1. Модели

- `GameRatingVote`: `game`, `user` (PROTECT), `value` 1–5 CHECK, `is_valid`,
  `moderated_by`, `reason`, `change_count_30d`, `change_window_started_at`,
  `created_at`, `changed_at`; `UNIQUE(game, user)`.
- `GameRatingAggregate`: `game` OneToOne, `total`, `count`, `average(3,2)`,
  `wr_score`, `distribution` JSONB, `recalculated_at`.

## 2. Правила (§2.9)

Голосовать может только активный зарегистрированный пользователь с
`UserGamePlaytime.verified_seconds ≥ Game.rating_min_playtime_seconds`
(иначе 403 `E_PLAYTIME_REQUIRED`), возраст аккаунта ≥1 ч, ≤20 оценок/сутки.
Одна строка на (game, user); повторное значение — идемпотентно; изменение —
не чаще 1/24 ч и ≤5/30 дней. Агрегат пересчитывается в транзакции под
advisory-lock по игре, учитывает только `is_valid` и активных
пользователей; `distribution` по 1–5. Гость видит агрегат, но голосовать не
может (403 `E_AUTH_REQUIRED`). При удалении аккаунта голоса удаляются,
агрегаты пересчитываются; заблокированные исключаются при пересчёте.

## 3. API

- `POST /api/v1/games/{id}/rating` — `{value:1..5}`, CSRF, auth,
  throttle `rating` 20/day; ответ `{average,count,distribution,my_vote}`.
- `GET /api/v1/games/{id}/rating/summary` — публичный агрегат + `my_vote`
  (для authenticated), throttle `rating_read` 120/min.

Названия полей и summary-путь помечены `[PROP]` до нормирования SDK/CRM
контракта.

## 4. Проверки

```text
pytest tests/integration/test_game_ratings.py -> 10 passed
pytest (full) -> 273 passed, 2 skipped
make lint -> All checks passed
make types -> Success: 318 source files
makemigrations --check -> No changes detected
```

Тесты: guest/no-playtime; агрегат; no-op; cooldown 24 ч; 5/30; 20/сутки;
невалидное значение; CSRF; blocked исключается; удаление пересчитывает;
возраст аккаунта; публичный summary; гонка первого голоса (advisory-lock);
параллельные голоса разных users (агрегат без потерь); включительный порог
playtime.

## 5. Остаточные риски

- Антифрод §2.9.6: возраст/лимиты/порог playtime реализованы; IP-серии,
  журнал подозрительной активности и очередь модерации — отдельный слой.
- Блокировка пользователя исключает голос только при пересчёте (recalc):
  автоматический пересчёт при блокировке — задача CRM/модерации.
- `wr_score` = средняя; взвешенный рейтинг (Wilson) — при появлении
  сортировки по рейтингу.
- `change_count_30d` хранится на строке голоса; при 30-дневном окне
  счётчик сбрасывается лениво.
