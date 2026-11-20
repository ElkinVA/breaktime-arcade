# API и публичные маршруты — фундамент

Документ фиксирует **фактически реализованные** маршруты dev-фундамента.
Плановый API `/api/v1/` из BA-PLAT-4.2 §2.23 пока не реализован: пустые
`api/views.py` и `config/api.py` не считать API.

## 1. Реализованные маршруты

| Метод | Путь | Назначение | Ответ |
|---|---|---|---|
| GET | `/healthz` | Liveness без БД | 200 `{"status":"ok"}` |
| GET | `/readyz` | Readiness: БД, cache, broker, i18n, backup | 200/503 + checks |
| GET | `/` | Выбор языка по `Accept-Language` | 302 `/<lang>/`, `Vary: Accept-Language`; 406/503 |
| GET | `/<lang>/` | Главная | 200 (шаблон) |
| GET | `/<lang>/games/` | Каталог | 200 (шаблон) |
| GET | `/<lang>/games/<slug>/` | Карточка игры | 200 JSON-заглушка `{"status":"stub"}` |
| GET | `/<lang>/games/<slug>/play/` | Игровой экран | 200 JSON-заглушка |
| GET | `/<lang>/games/<slug>/leaderboard/` | Рекорды | 200 JSON-заглушка |
| GET | `/<lang>/genres/<slug>/` | Жанр | 200 JSON-заглушка |
| GET | `/theme-<hash>.css` | CSS активной темы | 200 `text/css`, immutable; 404 |
| GET | `/crm/` | CRM dashboard | 302 на login без staff |
| GET | `/crm/login/` | CRM login | 200 каркас |
| GET | `/crm/logout/` | Выход | 302 на login |

Шаблоны каталога и CRM — каркас; JSON-заглушки не являются игровой
функциональностью.

## 2. Языковые URL

- Все публичные URL имеют префикс `/<lang>/` из активных языков БД.
- Корень `/` → 302 по `Accept-Language`; при отсутствии приемлемого языка —
  406; при отсутствии обязательного `en` или ошибке получения списка — 503.
- Неизвестный языковой префикс → 404; переключатель не переносит его в
  ссылку.
- `Vary: Accept-Language` выставляется на root/503.

Нормативная основа: BA-PLAT-4.2 §2.6, §2.15.

## 3. Плановый API `/api/v1/` — не реализован

BA-PLAT-4.2 §2.23 требует, среди прочего:

```text
POST /api/v1/sessions
POST /api/v1/sessions/{id}/activate
POST /api/v1/sessions/{id}/heartbeat
POST /api/v1/sessions/{id}/result
POST /api/v1/sessions/{id}/close
GET  /api/v1/games/{id}/leaderboard?limit=10
GET  /api/v1/games/{id}/me/best
GET  /api/v1/games/{id}/locales/{lang}
GET  /api/v1/games/{id}/storage
PUT  /api/v1/games/{id}/storage
POST /api/v1/games/{id}/rating
GET  /api/v1/catalog
POST /api/v1/reports
```

Эти маршруты относятся к этапам 3/5, не к текущему фундаменту. До их
реализации нельзя считать API готовым.

## 4. Аутентификация и разрешения

- DRF настроен deny-by-default: `IsAuthenticated`; публичные endpoint'ы
  должны явно объявлять `AllowAny` (BA-PLAT-4.2 §2.20, §2.23).
- API same-origin, без CORS; session authentication + CSRF.
- CRM использует staff-проверку в view; полноценные роли/2FA — этап 2.
- Гостевые запросы и игровые сессии — этап 3; сейчас не реализованы.

## 5. Ошибки

- `406` — нет приемлемого языка при корректном списке активных языков.
- `404` — неизвестный языковой префикс/маршрут.
- `503` — отсутствие обязательного `en` или ошибка получения активных языков;
  ответы 503 содержат `Vary: Accept-Language`.
- API-коды `E_*` из BA-PLAT-4.2 §2.23 относятся к плановому API и пока не
  реализованы.

## 6. Сессия и сообщения (BA-FOUNDATION-002)

Внешний JSON использует `sessionId`; внутренние Python/БД имена — `session_id`.
Проект протокола и все типы Приложения F: `docs/contracts/MESSAGE_PROTOCOL.md`,
`schemas/messages/*.json`. Нормативные примеры BA-PLAT §2.12.2/§2.23 с
`session_id` остаются зафиксированным расхождением до решения владельца.
