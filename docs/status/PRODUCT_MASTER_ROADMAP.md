# Master roadmap — Breaktime Arcade + AI Headquarters

**Дата:** 2026-11-26. **Основание:** owner-директива о переходе к полной
разработке продукта; BA-PLAT-4.2/BA-GAME-2.2/BA-SDK-1.1; фактические
`BACKLOG`, `PROJECT_STATUS`, `NOW`, `FIRST_WORKING_VERSION`.

Этот документ — единая карта крупных этапов. Он не заменяет ТЗ, backlog и
реестры; при конфликте приоритет у ТЗ и owner-решений.

## 1. Фактическая точка старта

- `main` = `0e7f141`, рабочее дерево чистое, `origin/main` синхронизирован.
- Полный Python gate: **1259 passed, 14 skipped, exit 0**; browser E2E
  **22 passed**; JS **31/31**; ruff/format/mypy clean; prod-style image
  собирается с Playwright.
- Работают: публичный каталог, аккаунты (partial), App F server slices,
  runtime/SDK, ZIP pipeline, CRM (partial), backup/restore, AI HQ sandbox,
  browser publish gate, isolated Redis broker, CI browser E2E.
- Игры в `games-src`: `archer`, `neon_snake`, `probe`.
  **Who's Undercover? отсутствует полностью** — это новая продуктовая игра,
  а не восстановление утраченного кода.

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

### P1. Live Room (платформенная зависимость)

Для игры на разных устройствах нужен новый контракт платформы: комната,
код входа, host/player роли, синхронизация состояния, reconnect, лимиты и
модерация. В BA-SDK-1.1 этого нет; game origin не может держать сервер.
Без owner-решения и нового API Live Room не маркетируется как готовый.

Минимальный контракт-кандидат: `ba:room.create/join/state/command`,
server-authoritative snapshot + sequence, host token, TTL, rate limits.
Реализация — отдельный P1-пакет после product decision.

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
