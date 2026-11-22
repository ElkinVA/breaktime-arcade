# Реестр нормативных расхождений

**Статус:** реестр BA-FOUNDATION-002. Нормативные ТЗ не изменялись.
Дата: 2026-11-19.

## C-001 — session_id / sessionId

| Поле | Значение |
|---|---|
| Источник 1 | BA-PLAT-4.2 §2.12.2: `postMessage {type:"ba:hello", protocol:1, session_id}` |
| Источник 2 | BA-PLAT-4.2 §2.23: `POST /sessions` → `{session_id, ticket, expires_at}` |
| Источник 3 | BA-PLAT-4.2 §2.12.4: `data.sessionId` |
| Источник 4 | BA-PLAT-4.2, Приложение F: `{..., requestId, sessionId, payload}` |
| Источник 5 | BA-GAME-2.2 §6: `ba.context.sessionId` |
| Класс | Противоречие внешнего именования |
| Решение владельца | Внешний JSON — `sessionId`; Python/БД — `session_id`; преобразование на границе |
| Что не изменено | Нормативные ТЗ; примеры с `session_id` остаются в тексте |
| Последствие | API/postMessage контракты проекта используют `sessionId`; нормативные примеры требуют будущей синхронизации |
| Файл проекта | `docs/contracts/SESSION_ID_PROTOCOL.md` |

## C-002 — два варианта BA-GAME-2.2

| Поле | Значение |
|---|---|
| Источник A | BA-GAME-2.2 внутри `technical_specification/ts_site.txt` |
| Источник B | `technical_specification/ts_game.txt` |
| Различие | A содержит дополнительный блок «Решения, принятые по умолчанию, и отклонения»; заголовок отличается |
| Класс | Дополнительное требование в A; технических противоречий нет |
| Решение | Architect (OD-AUTONOMY-006): canonical = **A**; B — историческое подмножество |
| Последствие | Единый внутренний baseline — A; исходные ТЗ не переписываются |
| Файлы проекта | `docs/audits/BA-GAME-2.2_COMPARISON.md`, `docs/decisions/ADR-APPF-001.md` |

## C-003 — отсутствие BA-SDK-1.1/BA-ENV-1.1

| Поле | Значение |
|---|---|
| Факт | Оригиналы отсутствуют в BA, AI Dev, docs и истории Git |
| Нормативная ссылка | BA-PLAT-4.2 преамбула/§2.3/§2.5/§2.14.3/§2.25; BA-GAME-2.2 §6 |
| Класс | Нормативный пробел, не противоречие текста |
| Решение | DRAFT проверены Pro-review; финальные v1.1.0 **внутренне приняты Architect** (ADR-APPF-001) |
| Последствие | SDK/схемы реализуются по v1.1.0; внешняя публикация/юридическое утверждение не выполнялись |
| Файлы проекта | `docs/contracts/BA-SDK-1.1_v1.1.0.md`, `docs/contracts/BA-ENV-1.1_v1.1.0.md`, `docs/decisions/ADR-APPF-001.md` |

## C-004 — формат payload сообщений

| Поле | Значение |
|---|---|
| Факт | BA-PLAT-4.2/BA-GAME-2.2 задают интерфейс и часть полей, но не полные payload-схемы всех App F типов |
| Класс | Нормативный пробел |
| Решение | game→host payload — strict (`additionalProperties:false`); `ba:context`/`ba:session` — additive, SDK игнорирует неизвестные поля; прочие сообщения ≤64 КиБ |
| Последствие | Схемы остаются deliverable этапа 3, но правила закрыты внутренним контрактом BA-SDK-1.1 v1.1.0/ADR |
| Файлы | `schemas/messages/*.json`, `docs/contracts/MESSAGE_PROTOCOL.md`, `docs/contracts/BA-SDK-1.1_v1.1.0.md` |

## C-005 — Docker digest базовых образов

| Поле | Значение |
|---|---|
| Факт | Python/Node base images не имеют локального digest; registry manifest inspect завершился таймаутом |
| Класс | Незакрытое требование воспроизводимости |
| Решение | Digest не выдумывается; требование зафиксировано как открытое |
| Последствие | Dockerfile нельзя считать полностью digest-pinned |
| Файл | `docs/contracts/BA-ENV-1.1_DRAFT.md` |
