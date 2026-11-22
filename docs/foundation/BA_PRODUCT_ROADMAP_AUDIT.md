# Browser Arcade / App F — сверка с ТЗ и приоритетная дорожная карта

**Дата:** 2026-11-22
**Основание:** BA-PLAT-4.2, BA-GAME-2.2 (A/B), BA-SDK-1.1, BA-ENV-1.1,
`docs/handoff/NOW.md`, `PROJECT_STATUS.md`, `BACKLOG.md`, `OWNER_DECISIONS.md`,
`RISK_REGISTER.md` и фактический код.

**Правило:** этот документ не меняет ТЗ. Он отделяет фактическое состояние от
нормативного плана и фиксирует крупные этапы, а не набор микрозадач.

## 1. Исходная точка

- `main` = `ac6d18f`; STOP установлен, автозапуск новых задач выключен.
- Свежая тестовая БД: `792 passed, 11 skipped` (см. §6 о reuse-db).
- Реализованные срезы значительно опережают старую формулировку
  `NOW.md`/`PROJECT_STATUS.md` «этап 0 частично, этап 1 не начат»: есть
  каталог, аккаунты, App F server slices, runtime A+B, ZIP preflight/extract/
  worker, CRM dashboard и продуктовые UI-срезы.
- Это **не означает** продуктовую приёмку или закрытие нормативных этапов.

## 2. Что реализовано и проверено технически

| Область | Фактическое состояние | ТЗ |
|---|---|---|
| Публичный каталог | Home, list, detail, genre, filters, search/FTS, tags, sorts, pagination, ratings/popularity display, localization badge, empty-search fallback | §2.6–2.8 |
| SEO | canonical, meta/OG/Twitter, sitemap-index по языкам, robots, hreflang/x-default | §2.19 |
| i18n | активные языки из БД, TranslationEntry/cache, fallback, языковые URL, DE/RU tests, CLDR plural helper в части среза | §2.15 |
| Аккаунты | регистрация/вход/выход, профиль, export/delete request, 2FA staff, recovery/regenerate; legal/email still incomplete | §2.10 |
| Leaderboard | публичный TOP-10, personal best/last 20, rank/date/trust display | §2.11 |
| App F API | sessions/activate/heartbeat/result/close, storage, leaderboard/me, ratings, popularity/playtime | §2.12–2.13 |
| Runtime | official SDK JS, host protocol, player host, play iframe, probe, E2E/host tests, eventLog/verifier baseline | §2.4.3, §2.12–2.13 |
| ZIP | preflight, extract, worker isolation, runtime publisher | §2.14.2–2.14.3 |
| CRM | login + operational dashboard counters | §2.16 (частично) |
| Infra | dev-lite/staging compose, health, backup/restore-check, Celery/Redis | §2.5 |

## 3. Категория A — можно реализовывать без внешнего решения

После делегирования Architect полномочий (2026-11-22) сюда входят технические
и продуктовые решения внутри ТЗ; они не требуют отдельного ответа владельца.

### A1. Закрыть нормативные контракты и ADR

- Выбрать канонический BA-GAME-2.2: **A** (`ts_site` §BA-GAME) как
  надмножество B; зафиксировать ADR, не менять `ts_site.txt`.
- Утвердить BA-SDK-1.1 и BA-ENV-1.1 как внутренние финальные контракты;
  закрыть Open Questions O3/O4 безопасным вариантом (64 КиБ, 429 challenge
  до реализации, HSTS после TLS).
- Зафиксировать App F: `sessionId`, ignore-unknown-fields, error codes,
  EventLog transport, storage If-Match, trust levels.
- Закрыть DB-001…DB-008 согласованными ADR; уже реализованные constraints
  не переписывать без миграционной необходимости.

### A2. Завершить публичный продукт

- Rating vote UI 1–5 звёзд с порогом playtime и guest invitation (§2.9).
- Leaderboard: TOP-100 с пагинацией и всегда видимой строкой пользователя
  (§2.11), сохраняя текущий personal section.
- SEO: structured data, 301 для смены slug, CRM-диагностика (§2.19).
- i18n: устранить one/other-only плюрализацию, добавить CLDR few/many и
  проверить 6 языков/узкие экраны (§2.15).
- Accessibility/performance budgets (§2.7), analytics event/partition layer
  (§2.18) — только в пределах ТЗ.

### A3. Завершить CRM и пайплайн

- CRM: games list/card tabs, wizard, validation report, import diff, users,
  ratings, complaints, translations, content/design, audit (§2.14, §2.16).
- Pipeline: importer, injection, bundling, critical path, autotest, publish/
  schedule/rollback; remove empty service stubs by implementing them (§2.14).
- Roles/2FA/step-up and email technical integration (§2.10, §2.16); legal
  wording remains a separate external item.
- Retention implementation per chosen policy (§2.22/§2.18), after legal
  confirmation.

### A4. Проверки и подготовка запуска

- Acceptance matrix §2.26, load/DR, CSP/rate-limit checks, E2E for public/CRM.
- Production requirements: domains/TLS/S3/CDN/monitoring/backup as a written
  requirement, not an external deploy.

## 4. Категория B — требует внешнего подтверждения/действия

Это не «технические вопросы»; Architect не подменяет юриста, провайдера или
владельца инфраструктуры.

| Направление | Пункт ТЗ | Необходимое внешнее действие | Последствие без него |
|---|---|---|---|
| Terms/Privacy, legal basis | §2.21, §2.10.2, §2.15 | Юридическая проверка и утверждение текстов, версии, DSA/EN 301 549, consent | Нельзя публиковать production-регистрацию/legal pages; нельзя закрыть этап 8 |
| Email delivery | §2.10.3 | Реальный провайдер, домен, SMTP/API credentials, bounce policy | Нет подтверждённого email, восстановления пароля и части §2.10 E2E |
| Domains/TLS/game origins | §2.4, §2.5, §2.20 | Регистрация доменов, DNS, TLS, серверы, secrets | Нет отдельного origin игры, staging/prod launch невозможен |
| S3/CDN/hosting/monitoring/DR | §2.5, §2.19, §2.24 | Аккаунты/квоты/credentials, backup storage | Нет production SLO, media/CDN, DR-учений |
| Paid external services / ads / external analytics | §2.17, §2.18, §2.21 | Договор/аккаунт, consent, cookies | Реклама/внешняя аналитика остаются выключены; не блокирует core |
| Реальная игра BA-GAME | §2.14, §2.25 этап 4 | Готовый ZIP/контент от игровой команды; лицензии/права | Нельзя принять полный путь ZIP→CRM→игра→рекорд→обновление |
| Production deployment | §2.5, §2.25 этап 8 | Явное разрешение и окно deploy | Код готов, но продукт не запущен |
| Telegram/Dev Control | вне продукта | Сеть/токен/прокси на VPS | Не влияет на Browser Arcade; только уведомления AI HQ |

## 5. Категория C — реализовано, нужна продуктовая приёмка

- App F server slices: SESSION-002, RESULT-001, LEADERBOARD-001, STORAGE-001,
  PLAYTIME-001, RATINGS-001, POPULARITY-001 — технически реализованы, часть
  review принята; owner/product acceptance остаётся.
- Runtime A+B: SDK/host/player/play view — **IMPLEMENTED / TECHNICAL REVIEW**;
  review incomplete; BA-SDK/ENV/GAME внутренне приняты в ADR-APPF-001, но
  product acceptance и внешние действия остаются.
- Catalog/SEO/i18n/account/CRM-dashboard UI-срезы — текущие тесты зелёные,
  требуют продуктовой выборочной приёмки на реальных данных.
- ZIP PREFLIGHT/EXTRACT/WORKER — техническая приёмка агента; продуктовая
  приёмка и реальный ZIP остаются.
- Accounts/2FA/profile/delete — PARTIAL: технические тесты есть, legal/email
  и часть ролей/step-up вне.
- CRM dashboard — технически принят; остальные CRM-экраны отсутствуют.

## 6. Очевидные противоречия в реестрах

1. `PROJECT_STATUS.md` §7 всё ещё говорит «этап 0 частично, этап 1 не начат»;
   фактически реализованы этапы 1–5 частично, но нормативные контракты не
   закрыты. Нужно читать это как историческую запись, не как текущую карту.
2. `BACKLOG`/`PROJECT_STATUS` строка `BA-CATALOG-001` перечисляет
   ratings/popularity/play как отсутствующие; они уже реализованы. Остаток —
   не все проверки §2.8/§2.11 (rating UI, TOP-100 pagination), не отсутствие
   ratings вообще.
3. `NOW.md` «Следующий шаг» описывает App F как не начатый; фактически
   серверные срезы и runtime A+B есть, но BA-SDK/ENV/GAME и полный product
   acceptance не закрыты.
4. Тестовая БД с `--reuse-db` может потерять data-migration seed’ы после
   `flush`; `make check` тогда ложно падает, `make test-fresh` проходит.
   Это test-infrastructure defect, не продуктовый; исправить детерминированной
   seed-фикстурой/очисткой.

## 7. Приоритетный план

| Приоритет | Крупный пакет | Результат |
|---|---|---|
| P0 | Contract/ADR closure | Канонические BA-SDK/ENV/GAME/DB/App F decisions recorded; больше не блокируют implementation — **DONE**: [ADR-APPF-001](../decisions/ADR-APPF-001.md) |
| P1 | Public product completion | Rating UI, TOP-100 leaderboard, SEO structured/redirects, i18n plural, accessibility/perf |
| P2 | CRM + package pipeline | Owner can run game list/wizard/import/validation/autotest/publish/rollback without code |
| P3 | Accounts/legal/email | Full §2.10 E2E after external legal/provider confirmation |
| P4 | Production | Domains/TLS/S3/CDN/monitoring/DR and signed launch checklist |

**Не начинать:** production deploy, legal publication, paid provider wiring or
real game acceptance without the external actions in §4.
