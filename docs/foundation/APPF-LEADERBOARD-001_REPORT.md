# APPF-LEADERBOARD-001 — публичный API таблицы рекордов

**Дата:** 2026-11-20  
**Статус:** IMPLEMENTED / AWAITING OWNER ACCEPTANCE; independent review —
`code-reviewer` и `security-auditor`: **accept**, блокеров нет.  
**Основание:** BA-PLAT-4.2 §2.11, §2.23; таблица `LeaderboardEntry` из
APPF-RESULT-001.

## 1. API

- `GET /api/v1/games/{technical_id}/leaderboard?limit=10|100` — TOP-N
  текущей эпохи + строка `me` (для authenticated), `me: null` для гостя.
- `GET /api/v1/games/{technical_id}/me/best` — личный рекорд
  (`value`, `achieved_at`, `rank`); без аутентификации → 403
  `E_AUTH_REQUIRED`.

Только published-игры; неизвестная/неопубликованная → 404. `limit` строго
`10` или `100`, иначе 400. Read-throttle `leaderboard_read` 120/min
(subject/IP) как hardening; Приложение E ставку для чтения не задаёт.

## 2. Порядок и ранг

Сортировка: `direction` игры (higher/lower), затем `achieved_at ASC`, затем
`user_id ASC` (§2.11.3). Ранг = число строго лучших + tie-break по
`user_id` + 1; совпадает с позицией в TOP-N и остаётся абсолютным вне топа.
Фильтр: `game`, текущая `epoch`, `is_public`; `is_test`/quarantine в таблицу
не попадают по построению RESULT-001.

## 3. Ответ

`{game_id, epoch, direction, entries:[{rank,nickname,value,achieved_at,
trust_level}], me}`. `user_id`/email/login не отдаются; nickname — только
отображаемое имя профиля. Удалённые аккаунты удаляются из таблицы при
анонимизации, осиротевших nickname нет.

## 4. Проверки

```text
pytest tests/integration/test_leaderboard_api.py -> 7 passed
pytest (full) -> 256 passed, 2 skipped
make lint -> All checks passed
make types -> Success: 318 source files
```

Тесты: higher/lower порядок, tie-break achieved_at, me-строка и совпадение
ранга с TOP-N, guest `me:null`, пустая таблица, epoch-изоляция, limit
10/100 и мусорный limit, published-only, `/me/best` для гостя.

## 5. Остаточные риски

- Read-DoS: throttle 120/min + индексы (game, epoch, ±value, achieved_at)
  частичные `is_public`; при росте — nginx/CDN.
- Pagination внутри TOP-100 не реализована: API отдаёт до 100 строк;
  клиентская пагинация — решение владельцу/порталу.
- `E_SESSION_INVALID` для «игра не найдена» — переиспользован существующий
  код; отдельный `E_GAME_NOT_FOUND` не вводился (§2.23).
- nickname публичен по продукту; не является производным от email/login.
