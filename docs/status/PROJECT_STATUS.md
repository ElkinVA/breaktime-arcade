# PROJECT_STATUS — Breaktime Arcade

**Дата актуализации:** 2026-11-20 (BA-AUTONOMY-003).  
Документ — краткая панель текущего состояния. Нормативные требования
определяются только утверждёнными ТЗ и решениями владельца; отчёты агентов,
аудиты и реестры не заменяют приёмку.

## 1. Текущий статус

**Проект находится в состоянии каркаса, не MVP.** Этап 0 формально **не
закрыт**; этап 1 **не завершён**. `BA-STAGE-1.1` — ограниченный срез этапа 1,
**NOT_ACCEPTED**. `BA-FIX-001` остаётся открытой, `BA-FIX-003` принят с
некритичными замечаниями.

Принятие **Documentation Block 1** (BA-DOC-001 + FIX-01/02/03) не означает
принятия технического этапа 0, этапа 1 или `BA-STAGE-1.1`. App F не
реализован и не готов к приёмке; `BA-APPF-002` **не запускалась**.

Технические пакеты **BA-I18N-002** и **BA-STAGE-1.2-E2E** выполнены и не
требуют решения владельца: языковой реестр переживает отказ Redis,
`language_url` не отдаёт 500 при недоступном реестре, широкие
`except Exception` в i18n-middleware/root убраны; browser/E2E проверяет
шесть языков, root redirect, 404, переключатель, 360px и healthz.
R-006/R-007 закрыты regression-тестами; R-003/R-004/R-005 остаются.
BA-STAGE-1.2-E2E зафиксирован как **IMPLEMENTED / AWAITING INDEPENDENT
REVIEW**, а не как приёмка.

**BA-STAGE-2.1** (регистрация, вход и профиль по §2.10) реализован в dev:
модели/миграция аккаунтов, регистрация, вход/выход, подтверждение email,
нейтральное восстановление пароля, смена пароля с инвалидацией сессий,
профиль/настройки, экспорт JSON, запрос удаления с окном 7 дней и Celery-
анонимизация, Argon2id, HIBP-hook и rate limits. Пакет имеет статус
**PARTIAL**, а не Done: отсутствуют утверждённые юридические тексты/версии,
история игр и личные рекорды (модели gameplay/leaderboards ещё не
реализованы), обработка bounce и полный cleanup игровых данных; анонимная
идентичность подготовлена сервисом, но не подключена к запросам, требующим
субъекта. 2FA персонала в этот пакет не входила.

**BA-STAGE-2.2** (2FA персонала) реализован в dev как **PARTIAL**:
TOTP-секрет, обязательный enrollment для staff, двухшаговый вход,
recovery-коды (10, hash, single-use), защита от replay, отключение через
password+TOTP, инвалидация прочих сессий, уведомление на verified email и
middleware, не пропускающий staff-сессию без подтверждённой 2FA. Owner
recovery и `LoginEvent` добавлены в 2.4; остаются роли/CRM step-up,
уведомления о смене ролей и browser E2E staff-сценариев.

**BA-STAGE-2.3** (browser E2E аккаунтов) — **IMPLEMENTED / AWAITING
INDEPENDENT REVIEW**: 2 E2E-сценария (регистрация → профиль → export →
logout/login → смена пароля → login с новым паролем → deletion request/
cancel; отказ формы без согласия) прошли на dev-стеке. Полный E2E-набор —
13 passed (11 shell + 2 account). Это не приёмка §2.10/2FA: legal texts,
game history/records, bounce/provider и роли/CRM step-up остаются.

**BA-STAGE-2.4** (2FA completion) — **PARTIAL**: добавлены офлайн-код
владельца (только superuser, одноразовый, после использования требует
повторного enrollment), `LoginEvent` без plaintext login/IP, regeneration
recovery-кодов через password+TOTP, события enable/disable/recovery.
Остаются роли и CRM step-up (CRM — stub), уведомления о смене ролей и
шифрование TOTP-секрета; retention закрыт в 2.5.

**BA-STAGE-2.5** (retention cleanup) — **PARTIAL**: Celery Beat
`accounts.cleanup_expired_account_records` удаляет истёкшие
`AnonymousIdentity`/`AccountToken`, `LoginEvent` старше 365 дней и
`NicknameReservation` с истёкшим сроком; reservation теперь использует
`NICKNAME_RESERVATION_DAYS=730`. Не покрыты `SecurityEvent` (App F),
`GameStorage`/`GameSession`, mail-логи, бэкапы и согласия — их модели/
владельцы сроков ещё не реализованы.

**BA-QUALITY-001** (coverage) — добавлен `make coverage`, конфигурация
`coverage.run/report` с порогом 70 % и `fail_under=70`; фактический общий
coverage — **81.65 %** (2594 statements, 476 missed) при 177 passed,
2 skipped. Низкие модули: `hibp.py` 39 %, `health.py` 59 %, `ba_i18n.py`
63 %, `coverage.py` 36 %, `theme/views.py` 40 %, `storage.py` 0 %;
порог по совокупности выполнен, но это не независимая проверка и не
закрывает пробелы по отдельным модулям.

**BA-CATALOG-001** (публичный каталог) — **PARTIAL**: список только
`published`, фильтры по основному жанру/мобильной поддержке/длительности,
поиск по локализованным названию/описанию (минимум 2 символа), сортировка
new/old, локализованный detail с fallback `en`, genre page и HTMX partial.
Не реализованы: дополнительные жанры и теги (в моделях нет M2M), FTS/
`pg_trgm`-ранжирование, рейтинг/популярность/число голосов (нет моделей
ratings/leaderboards), бейдж покрытия локализации, play-кнопка (App F).
5 integration tests.

**BA-CATALOG-002** (жанры/теги) — **IMPLEMENTED / AWAITING INDEPENDENT
REVIEW**: добавлены additive-модели `GameGenre`/`GameTag` (M2M через
таблицы), фильтры по дополнительному жанру и тегам, tag options в форме,
миграция `catalog.0003` применена; 6 integration tests. FTS/`pg_trgm`,
ratings/popularity и play остаются вне пакета.

**BA-CATALOG-003** (FTS/`pg_trgm`) — **PARTIAL**: поиск использует
`SearchVector`/`SearchQuery` с конфигурацией языка (или `simple`),
`TrigramSimilarity` и прежний `icontains` fallback; 7 integration tests.
Вектор вычисляется в запросе, `GameTranslation.search_vector` не
заполняется, отдельного GIN-индекса для выражения нет, `unaccent` в
запросе не применяется — производительность/ранжирование не нормативные.

**BA-CATALOG-004** (persisted vector) — **PARTIAL**: `GameTranslation`
обновляет `search_vector` через post_save (simple, weights A/B/C);
добавлена data-migration `catalog.0004` для backfill существующих строк;
поиск использует stored vector + GIN, query-time FTS/trigram остаётся
fallback. Не реализованы `unaccent`, `SearchRank`-ранжирование, обновление
при bulk/import и проверка плана запроса на объёме.

**BA-CATALOG-005** (unaccent/ranking/bulk) — **IMPLEMENTED / AWAITING
INDEPENDENT REVIEW**: `unaccent()` применяется в persisted vector и
запросе; `SearchRank` задаёт порядок при поиске; Celery Beat
`catalog.refresh_catalog_search_vectors` пересчитывает vector после
bulk/import; backfill-миграция `catalog.0005`; 8 integration tests. План
запроса на объёме и ratings/popularity/play остаются.

## 1.1. AI infrastructure — BA-AUTONOMY-003

**BA-AUTONOMY-003** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**.
Основная сессия остаётся Flash; Pro (`architect`, `code-reviewer`,
`security-auditor`) работает в text-only режиме: Flash передаёт бриф,
Pro возвращает план/вердикт без tool-вызовов. Причина — реальный Pro
вызов маршрутизируется, но tool-использование ненадёжно (`leading-only`).
`ANTHROPIC_DEFAULT_OPUS_MODEL` изменён на `deepseek-v4-pro` (backup
`~/.bashrc`); Sonnet/Haiku/subagent default — Flash. Добавлены
`ba-plan`, `bash_guard.py`, guard для `ai-dev`, `NOW.md`; исправлены
указатели `docs/spec` → `technical_specification/`. Текущий полный suite —
185 passed, 2 skipped, coverage 82,34 %; реестровые 81,65 %/177 —
исторический срез BA-QUALITY-001. Детали —
`docs/foundation/BA-AUTONOMY-003_REPORT.md`.

## 2. Статусы работ

| Работа | Статус | Что означает |
|---|---|---|
| Documentation Block 1 (BA-DOC-001 + FIX-01/02/03) | **ACCEPTED** | Документация принята владельцем; техническая приёмка не следует |
| BA-FIX-003 | **ACCEPTED** с некритичными замечаниями | AUD3-001/AUD3-002 закрыты в BA-I18N-002; AUD3-003/005 остаются |
| BA-FIX-001 | **NOT_ACCEPTED** / открыта | Часть A-001/A-003 исправлена; формального закрытия владельцем нет |
| BA-FIX-002 | **PARTIAL** | Первоначальное исправление R-002; не является окончательным устранением |
| BA-I18N-002 | **COMPLETED**; не принят | R-006/R-007 закрыты; 147 tests; R-003/R-004/R-005 остаются |
| BA-STAGE-1.2-E2E | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | 11 browser/E2E passed на dev-стеке; CI/обычный suite по умолчанию skip; не приёмка |
| BA-STAGE-2.1 | **PARTIAL**; core §2.10 реализован, не принят | 17 account integration + 4 service tests; blockers: legal texts/versions, game history/records models, bounce, anonymous request wiring |
| BA-STAGE-2.2 | **PARTIAL**; TOTP 2FA персонала реализована, не принята | 9 2FA integration tests суммарно с 2.4; остаются roles/CRM step-up, encryption, E2E staff |
| BA-STAGE-2.3 | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | 2 account E2E + 11 shell E2E passed на dev-стеке; не приёмка |
| BA-STAGE-2.4 | **PARTIAL**; owner recovery, LoginEvent, regeneration реализованы | 9 2FA integration tests; roles/CRM step-up остаются |
| BA-STAGE-2.5 | **PARTIAL**; account retention cleanup реализован | 1 retention test; SecurityEvent/GameStorage/mail/backup/consent сроки не покрыты |
| BA-QUALITY-001 | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | `make coverage`; 81.65 % при пороге 70 %; низкие модули перечислены |
| BA-CATALOG-001 | **PARTIAL**; публичный список/фильтры/поиск/detail/genre/HTMX | 5 integration tests; missing FTS/ratings/popularity/App F |
| BA-CATALOG-002 | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | M2M `GameGenre`/`GameTag`, фильтры; 6 integration tests; без FTS/ratings/play |
| BA-CATALOG-003 | **PARTIAL**; FTS+trigram+language config | 7 tests; query-time vector |
| BA-CATALOG-004 | **PARTIAL**; persisted vector/GIN/backfill | 7 tests; unaccent/ranking/bulk добавлены в 005 |
| BA-CATALOG-005 | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | unaccent, SearchRank, bulk refresh; 8 tests; нет benchmark |
| BA-STAGE-1.1 | **NOT_ACCEPTED** | Ограниченный срез этапа 1; не самостоятельный нормативный этап |
| BA-FOUNDATION-001 | **COMPLETED**; не принят | Отчёт Partial/Blocked; независимая проверка выявила ограничения; этап 0 не закрыт |
| BA-FOUNDATION-002 | **PARTIAL / BLOCKED** | DRAFT-контракты и design-схема есть; оригиналы SDK/ENV и утверждение отсутствуют |
| Предыдущий аудит App F | **COMPLETED** | Отчёт существует; вывод: runtime App F отсутствует, проверены только схемы/валидатор |
| BA-APPF-001 | **COMPLETED**; не принят | Подготовлены 45 проектных решений; 29 Blocker, 17 вопросов владельцу |
| BA-APPF-002 | **NOT_STARTED** | Не запускалась; не отражать как выполненную |
| BA-AUTONOMY-003 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Pro text-only plan done; guards; NOW; docs pointers; 185 tests; security review **accept**; owner acceptance pending |
| BA-DOC-002 | **COMPLETED**; не принят | Актуализация шести реестров; ожидает проверки владельцем |

Статусы `COMPLETED`, `ACCEPTED`, `PARTIAL` и `NOT_ACCEPTED` не
взаимозаменяемы: завершение работы, техническая готовность и приёмка — разные
события.

## 3. Что фактически готово

- core: UUIDv7/citext, middleware/CSP, JSON-логи, healthz/readyz, storage.
- accounts: `User` + Argon2id, `UserProfile`, `EmailAddress`,
  `NicknameHistory`/`NicknameReservation`, `AccountToken`,
  `AnonymousIdentity`, `UserLegalAcceptance`; регистрация/вход/выход,
  email verification, password reset, профиль, смена пароля, экспорт,
  deletion request/cancel, Celery-анонимизация; BA-STAGE-2.1 — **PARTIAL**.
- 2FA персонала: TOTP, обязательный enrollment, recovery-коды, replay-
  protection, disable через password+TOTP, staff-middleware, owner offline
  code, `LoginEvent` и regeneration; BA-STAGE-2.2/2.4 — **PARTIAL** из-за
  отсутствующих ролей/CRM step-up.
- Retention: Celery cleanup для гостей, токенов, `LoginEvent` и nickname-
  резервов; BA-STAGE-2.5 — **PARTIAL** (глобальные сроки §2.22 не все).
- Coverage: `make coverage`, порог 70 %, фактически 81.65 %; CI-команда
  `pytest --cov=apps` читает конфигурацию; BA-QUALITY-001 — implemented.
- Catalog: published-only list, primary genre/mobile/duration filters,
  localized search (min 2), new/old sort, detail fallback `en`, genre page
  и HTMX partial; BA-CATALOG-001 — **PARTIAL**. Дополнительные жанры и
  теги (M2M), фильтры — BA-CATALOG-002; FTS+trigram — BA-CATALOG-003;
  persisted `search_vector`/GIN — BA-CATALOG-004; `unaccent`/ranking/bulk —
  BA-CATALOG-005.
- Browser E2E: регистрация/вход/смена пароля/deletion window; полный набор
  13 E2E passed; BA-STAGE-2.3 — **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**.
- Публичная i18n-оболочка и языковая маршрутизация BA-STAGE-1.1
  реализованы, но этап не принят.
- catalog: модели/миграции; публичные detail/play/leaderboard — JSON-заглушки.
- i18n: шесть языков, словари, middleware, тесты; BA-I18N-002 добавил
  устойчивый языковой реестр и regression-тесты R-006/R-007; R-002 имеет
  ограниченную доказательную базу, R-003/R-004/R-005 остаются.
- theme: токены → CSS; CRM: backup/restore-check; dev-lite и staging nginx.
- BA-FOUNDATION-002: DRAFT SDK/ENV, message schemas, semantic validator,
  SQL/ERD design, App J mapping; это **не** работающая App F.

## 4. Что не готово

- App F runtime: `apps/gameplay`, `apps/leaderboards`, `apps/ratings`,
  `sdk/1.1.0/ba-sdk.js`, `static/src/js/host_protocol.js` и
  `static/src/js/player.js` пусты/0 байт.
- SDK 1.1 и BA-ENV-1.1: оригиналы отсутствуют; DRAFT не утверждены.
- App F: postMessage, origin/source, sessionId/requestId runtime, states,
  idempotency, leaderboard, storage, EventLog/verifier и rate limit не
  реализованы. Наличие схем и `apps/core/contracts.py` не является сквозной
  системой.
- Аккаунты §2.10: утверждённые тексты/версии Terms и Privacy, страницы
  `/legal/terms/` и `/legal/privacy/`; история игр, личные рекорды и места;
  обработка bounce/недоставляемых адресов; удаление `GameResult`/
  `LeaderboardEntry`/`GameRatingVote`/`GameStorage`/`UserGamePlaytime`
  (модели ещё не реализованы); подключение `AnonymousIdentity` к первому
  запросу, требующему субъекта; 2FA персонала: офлайн-код восстановления
  владельца, отдельный журнал входов/SecurityEvent, уведомления о смене
  ролей и CRM step-up.
- Каталог: рейтинг/популярность/голоса, бейдж покрытия, публичный play
  runtime, benchmark/план запроса на объёме. Persisted vector/GIN,
  unaccent/ranking/bulk и M2M жанров/тегов есть.
- `/api/v1/`, полноценные CRM/2FA/роли, модерация, аналитика, pipeline,
  production compose/Nginx/monitoring/WAL/PITR/S3.
- SQL design не реализован в Django-моделях/миграциях; DB-001…DB-008
  требуют исправлений до App F (см. BA-APPF-001).

## 5. Блокирующие вопросы

1. **BA-SDK-1.1 и BA-ENV-1.1** отсутствуют; DRAFT не являются нормой.
2. **BA-GAME-2.2**: два варианта, канонический не выбран.
3. **App F contract gaps**: `myBest`, `autotest:finish`, `ba.fail`,
   pre-session `ba:error`, paused/failed, payload-схемы и лимиты.
4. **SQL/App J**: удаление пользователя/XOR, result↔session,
   leaderboard↔result, mode↔subject, фактический размер storage, immutable
   GameVersion, длина названия.
5. **Production infrastructure**: compose.prod, production Nginx,
   monitoring, WAL/PITR/S3, backup target.
6. **Docker base images** Python/Node не digest-pinned.
7. **Git remote/backup** отсутствуют; рабочее дерево в основном
   uncommitted/untracked.
8. **Legal texts/versions** для Terms/Privacy отсутствуют; в настройках
   используется `draft`. Утверждать текст и версии должен владелец/юрист.
9. **Email provider/bounce policy** не заданы; без них нельзя завершить
   §2.10.3 и подтвердить недоставляемые адреса.
10. **2FA персонала** реализована частично; остаются роли и CRM step-up,
    уведомления о смене ролей, шифрование TOTP-секрета и retention cleanup
    (`LoginEvent`/`AnonymousIdentity`/токены); глобальные сроки
  `SecurityEvent`/`GameStorage`/`GameSession`/mail-логов/бэкапов/согласий.

## 6. Решения, необходимые от владельца

1. Утвердить BA-SDK-1.1/BA-ENV-1.1 либо официально ограничить контрактный
   baseline; решить legacy `session_id`.
2. Выбрать/утвердить канонический BA-GAME-2.2. Не выбирать его исполнителем.
3. Утвердить или отклонить решения `BA-APPF-001` (45 предложений; особенно
   paused/failed, `myBest`, `autotest:finish`, `ba.fail`, лимиты сообщений,
   EventLog transport, SQL-исправления, preview subject).
4. Утвердить порядок SQL-исправлений DB-001…DB-008 до App F-миграций.
5. Определить production-домены/TLS, S3/CDN, monitoring, backup и WAL/PITR.
6. Решить судьбу остаточных R-003/R-004/R-005; AUD3-001/AUD3-002 и
   R-006/R-007 закрыты технически в BA-I18N-002.
7. Определить, когда формально закрывать этап 0/этап 1; самостоятельно не
   назначать следующий этап.
8. Принять или вернуть BA-DOC-002 и обновлённые реестры.
9. Утвердить юридические тексты Terms/Privacy и их версии для
   `TERMS_VERSION`/`PRIVACY_VERSION`; решить, публиковать ли `/legal/*`.
10. Утвердить транзакционного email-провайдера и политику bounce.
11. Утвердить роли и CRM step-up (включая уведомления о смене ролей);
    owner recovery и `LoginEvent` реализованы в dev, retention/шифрование
    остаются.

## 7. Следующий согласованный шаг

**Не начинать этап 1 целиком и не запускать BA-APPF-002.** BA-STAGE-2.1,
2.2, 2.4 и 2.5 доведены до **PARTIAL**; приёмка §2.10/2FA требует решений
владельца по legal texts и email provider (§6.9–6.10), процесса офлайн-
восстановления (§6.11), а также моделей gameplay/leaderboards для истории и
cleanup. Следующий незаблокированный пакет — `BA-QUALITY-002`
(поисковый benchmark/EXPLAIN на объёме, GIN для unaccent-выражения,
подъём покрытия `hibp/health/storage/theme`); он не требует App F.
Рейтинги/популярность/play и CRM-роли/step-up остаются заблокированы
App F и решениями владельца.
Параллельно владелец проверяет `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md`
и DRAFT-контракты, принимает решения по §6; только затем — отдельное задание
на SQL-исправления/App F. До этого App F не считать готовым к реализации или
приёмке.

## 8. Ссылки

- [TASK_HISTORY](../tasks/TASK_HISTORY.md)
- [OWNER_DECISIONS](../decisions/OWNER_DECISIONS.md)
- [AUDIT_REGISTER](../audits/AUDIT_REGISTER.md)
- [RISK_REGISTER](../risks/RISK_REGISTER.md)
- [CONTEXT_RECOVERY](../handoff/CONTEXT_RECOVERY.md)
- BA-FOUNDATION-001: `BA-FOUNDATION-001_REPORT.md` (корень; запрошенный
  `docs/foundation/BA-FOUNDATION-001_REPORT.md` отсутствует).
- BA-FOUNDATION-002: `docs/foundation/BA-FOUNDATION-002_REPORT.md`
  (запрошенный `reports/...` заблокирован guard-хуком).
- App F audit: `docs/foundation/BA-AUDIT-APP-F-REPORT.md`.
- App F prep: `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md`.
- BA-STAGE-2.1 report: `docs/foundation/BA-STAGE-2.1_REPORT.md`.
- BA-STAGE-2.2 report: `docs/foundation/BA-STAGE-2.2_REPORT.md`.
- BA-STAGE-2.4 report: `docs/foundation/BA-STAGE-2.4_REPORT.md`.
- BA-STAGE-2.5 report: `docs/foundation/BA-STAGE-2.5_REPORT.md`.
- BA-QUALITY-001 report: `docs/foundation/BA-QUALITY-001_REPORT.md`.
- BA-CATALOG-001 report: `docs/foundation/BA-CATALOG-001_REPORT.md`.
- BA-CATALOG-002 report: `docs/foundation/BA-CATALOG-002_REPORT.md`.
- BA-CATALOG-003 report: `docs/foundation/BA-CATALOG-003_REPORT.md`.
- BA-CATALOG-004 report: `docs/foundation/BA-CATALOG-004_REPORT.md`.
- BA-CATALOG-005 report: `docs/foundation/BA-CATALOG-005_REPORT.md`.
- Нормативные ТЗ: `technical_specification/ts_site.txt`,
  `technical_specification/ts_game.txt`.

## 9. Git-снимок BA-CATALOG-005

```text
Branch: main
HEAD: 1fc96b40b6c11b1fcb20e1e5a833a65d166c8340
Status entries: 163 (101 modified, 62 untracked)
Staged: 0
Remote: отсутствует
```

Снимок read-only; существующие пользовательские изменения сохранены;
`git add`/commit/reset/checkout/restore не выполнялись. Значительная часть
изменений относится к предыдущим пакетам и остаётся uncommitted.

## 10. Ограничения доказательной базы

- Отчёт агента, независимый аудит и приёмка владельцем — разные источники.
- Отдельные первичные отчёты BA-FIX-001/002/003 и BA-AUDIT-002/003 в файлах
  не найдены; сведения в реестрах не выдаются за полный лог.
- BA-FOUNDATION-001: отчёт есть в корне; ограничения независимой проверки
  зафиксированы по постановке BA-DOC-002, отдельный файл независимой
  проверки не найден.
- `reports/BA_AUDIT_20261118_162920.zip` — generated-отчёт, в котором
  BA-FIX-001 обозначен как настройка AI-среды; это не отчёт о i18n-фиксах и
  не доказательство приёмки.
- Тесты BA-FIX-003 в документационных задачах не перезапускались; их
  результаты остаются заявленными исполнителем.
- Этап 0 не закрыт; App F не реализован; BA-APPF-002 не запускалась.
- BA-STAGE-2.1: результаты тестов/lint/mypy/check и HTTP-проверок
  зафиксированы в `docs/foundation/BA-STAGE-2.1_REPORT.md`; это self-check
  исполнителя, не независимый аудит и не приёмка §2.10.
- BA-STAGE-2.2/2.4: 9 2FA integration tests; full suite — 177 passed,
  2 skipped (оба E2E-модуля skip без BA_E2E); отчёты —
  `docs/foundation/BA-STAGE-2.2_REPORT.md` и
  `docs/foundation/BA-STAGE-2.4_REPORT.md`.
- BA-STAGE-2.5: 1 retention test; отчёт —
  `docs/foundation/BA-STAGE-2.5_REPORT.md`.
- BA-QUALITY-001: `make coverage` — 81.65 % при пороге 70 %; отчёт —
  `docs/foundation/BA-QUALITY-001_REPORT.md`.
- BA-CATALOG-001…005: 8 integration tests; full suite — 185 passed,
  2 skipped; отчёты — `docs/foundation/BA-CATALOG-001_REPORT.md` …
  `BA-CATALOG-005_REPORT.md`.
