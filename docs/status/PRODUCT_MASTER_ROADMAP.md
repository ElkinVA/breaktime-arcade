# Master roadmap — Breaktime Arcade + AI Headquarters

**Дата:** 2026-11-26. **Основание:** owner-директива о переходе к полной
разработке продукта; BA-PLAT-4.2/BA-GAME-2.2/BA-SDK-1.1; фактические
`BACKLOG`, `PROJECT_STATUS`, `NOW`, `FIRST_WORKING_VERSION`.

Этот документ — единая карта крупных этапов. Он не заменяет ТЗ, backlog и
реестры; при конфликте приоритет у ТЗ и owner-решений.

## 0. Owner priorities approved 2026-11-26

1. **Live Room** — главный платформенный приоритет: спроектировать и
   реализовать server-authoritative комнаты, не ломая BA-SDK-1.1 и
   Pass & Play.
2. **Who's Undercover?** — параллельная продуктовая полировка: 6 языков,
   300+ проверенных пар, баланс, UX/анимации/звук, плейтесты.
3. **Version evidence** — изолированная среда для проверки именно 1.0.1 без
   обхода `V_PUBLISHED_UPDATE_BLOCKED`.
4. **AI HQ** — no-progress/stuck detection, recovery, context preservation,
   auto-next READY, weekly health metrics.
5. **Platform release** — hosted CI evidence, genre catalog, production
   checklist, monitoring, release readiness.

## 1. Фактическая точка старта

- `main` = `80fbcc2` (Live Room backend + additive SDK 1.2 transport),
  рабочее дерево чистое, `origin/main` синхронизируется push.
- Полный Python gate: **1281 passed, 15 skipped, exit 0 (617 s)**; JS
  **40/40**; browser E2E **25 passed** (last recorded); ruff/format clean
  (501), mypy clean (406).
- Работают: публичный каталог, аккаунты (partial), App F server slices,
  runtime/SDK, ZIP pipeline, CRM (partial), backup/restore, AI HQ sandbox,
  browser publish gate, isolated Redis broker, CI browser E2E.
- Игры в `games-src`: `archer`, `neon_snake`, `probe`, `whos_undercover`
  (Pass & Play 1.0.1, CODE-REVIEW ACCEPT).

## 2. Продуктовая инвентаризация

| Область | Состояние | Чего не хватает для публичного релиза |
|---|---|---|
| Портал/каталог | технически готов, E2E | контент, продуктовые тексты, legal, аналитика |
| Аккаунты | PARTIAL | email-провайдер, полный legal, часть истории/рекордов |
| App F API/runtime | технически готов | продуктовая приёмка; контент игр |
| CRM/pipeline | PARTIAL | draft isolation, prod deploy, контент-редакторы |
| Игры | 2 игровых картриджа + probe | Who's Undercover? и дальнейший портфель |
| UX | базовая, E2E | полировка плеера, ошибки, мобильные сценарии |
| Production | не задеплоен | домены/TLS/nginx game hosts/secrets/DR |

## 3. Who's Undercover? — продуктовая программа

### P0. Pass & Play MVP (первый READY-пакет)

Играбельная законченная версия на одном устройстве:

- setup 4–12 игроков, имена, 1–3 Undercover, опциональный Mr. White;
- категории слов и детерминированная раздача ролей;
- приватное раскрытие роли с передачей устройства;
- раунды подсказок с таймером, тайное голосование, раскрытие eliminated;
- проверки победы (все чужие устранены / чужие сравнялись / Mr. White
  угадал слово), финальный reveal;
- replay с теми же игроками и new game;
- мобильный layout, клавиатура, reduced-motion, звук WebAudio;
- SDK handshake, `ready`, storage настроек, pause/resume, new session;
- пакет BA-GAME-2.2, catalog/locales en+ru, обложка/2 скриншота;
- JS unit tests движка + browser E2E Pass & Play smoke;
- публикация через ZIP pipeline в dev.

**Критерий завершения:** новая игра импортируется через pipeline, играется
от setup до replay на 360 px и desktop, JS-тесты и E2E зелёные, независимый
review принят; Live Room явно помечен как зависимость платформы.

### P1. Live Room (платформенный приоритет)

Owner-директива 2026-11-26: Live Room — главный следующий платформенный
приоритет. BA-SDK-1.1 не содержит room API; game origin не может держать
сервер. ADR-LIVE-ROOM-001 выбран и реализуется.

- **LR-0/LR-1 (backend):** `apps/rooms` — Room/RoomMember/RoomCommand,
  create/join/leave, lobby ready/start, server-authoritative роли/слова,
  sanitized snapshots, reveal/clues/vote/tie/Mr. White/win/restart,
  requestId/expectedVersion, TTL/cleanup, host transfer/stale-host claim,
  account-deletion scrub, CSRF/throttles/no-store; integration tests.
- **LR-2a (transport, done):** additive SDK 1.2 `ba:room`/`ba:room:data`,
  `room.create/join/state/command/leave`, CSRF host bridge, tested mapping,
  nested-JSON guard, separate rate bucket; SDK 1.1 and Pass & Play unchanged.
- **LR-2b (next):** Live Room game UI and two-browser E2E.
- **LR-3:** load/crash, observability, product acceptance.

Live Room не маркетируется как готовый до LR-2b/LR-3 и продуктовой приёмки.

### P2. Контент, баланс, арт, пользовательские тесты

- 6 языков UI/слов или явный fallback-бейдж;
- 300+ пар слов по категориям, рейтинг качества;
- анимации/звук/визуальная система, projector layout;
- плейтесты, телеметрия только в рамках ТЗ, баланс 4–12 игроков;
- доступность и performance budgets.

## 4. Платформа и другие игры

1. Стабилизировать и продуктивно принять App F/каталог/аккаунты.
2. Закрыть draft isolation §4.1 (обновления опубликованных игр) и PB
   `is_public` — owner-решения.
3. Production deploy: домены/TLS/nginx game hosts, secrets, S3/CDN,
   monitoring, backup/DR.
4. После Who's Undercover? — следующий картридж по продуктовой ценности;
   добавление только ZIP-пайплайном.

## 5. AI Headquarters — развитие автономности

Каждая возможность должна давать измеримый эффект; инфраструктура ради
инфраструктуры запрещена.

| Направление | Ближайший измеримый шаг |
|---|---|
| Анализ состояния | автоматический weekly health snapshot: тесты, E2E, CI, незакрытые риски |
| READY-задачи | дедупликация и приоритизация по product impact/security |
| Координация агентов | bounded tasks, timebox, no-progress detection, cancel |
| Реализация | sandboxed developer/QA, evidence-based checks |
| Review | независимый Pro-review, запрет self-review |
| Тесты | targeted + full gate + E2E по типу изменения |
| Git/release | safe commit/push, branch protection evidence, no force |
| Recovery | journal/checkpoint, crash resume, orphan cleanup |
| Контроль циклов | budget/timeout/stuck detection, one task at a time |
| Отчётность | проверяемые отчёты с фактами и residual risks |

## 6. Ближайшие этапы и критерии

| Этап | Результат | Критерий завершения |
|---|---|---|
| E1 | Who's Undercover? Pass & Play MVP | **COMPLETED / CODE-REVIEW ACCEPT**: пакет 1.0.1 импортирован/опубликован в dev, 4–12 игроков, JS 12/12, E2E 3/3, full browser 25/25; product acceptance pending |
| E2 | Live Room contract decision | owner выбирает API/объём; без этого не обещаем Live Room |
| E3 | Контент/локали/арт/плейтесты | 6 языков или fallback-политика, 300+ пар, UX-приёмка |
| E4 | Платформенная стабилизация | draft isolation/PB решения, production checklist |
| E5 | AI HQ continuous loop | 2 недели автономных пакетов с метриками и без потери контекста |

## 7. Owner-гейты

Production deploy/домены/TLS, legal/email, paid services, реальные
пользовательские данные, draft isolation schema, PB `is_public`, Live Room
контракт, публикация игры как продукта. Всё остальное в рамках директивы
решается инженерно и фиксируется в реестрах.
