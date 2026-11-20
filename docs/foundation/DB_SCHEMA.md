# Проектная схема БД BA-FOUNDATION-002

**Статус:** DRAFT / DESIGN ONLY. Схема не применяется миграцией и не является
реализацией этапов 1–4. Нормативный источник: BA-PLAT-4.2 §2.22; контракт
полей — Приложение J.

Дата: 2026-11-19.

## 1. Артефакты

- SQL DDL: [`ba_schema.sql`](ba_schema.sql) — проектная PostgreSQL-схема.
- ERD: [`ERD.md`](ERD.md) — Mermaid-диаграмма.
- App J mapping: [`../contracts/APP_J_FIELD_MAPPING.md`](../contracts/APP_J_FIELD_MAPPING.md).
- SDK protocol: [`../contracts/MESSAGE_PROTOCOL.md`](../contracts/MESSAGE_PROTOCOL.md).

## 2. Общие правила

| Правило | Реализация в DDL |
|---|---|
| UUIDv7 для обычных сущностей | `uuid PRIMARY KEY DEFAULT uuidv7()` |
| BIGINT identity для событий | `analytics_event`, `security_event`, `admin_audit_log`, `moderation_action` |
| UTC | все `timestamptz`; приложение/БД использует UTC |
| `created_at`/`updated_at` | у обычных сущностей; immutable версии без `updated_at` |
| Ограничения | `CHECK`, `UNIQUE`, `FOREIGN KEY`, partial indexes |
| Каскады | явные: `CASCADE`, `SET NULL`, `RESTRICT` |
| Поиск | `tsvector` + GIN для `catalog_game_translation`; `pg_trgm` расширение |
| Секреты | в схеме отсутствуют; хеши/токены только как opaque text |

## 3. Перечень сущностей §2.22

### Аккаунты и языки

`accounts_user`, `accounts_recovery_code`, `accounts_profile`,
`accounts_nickname_history`, `accounts_nickname_reservation`,
`accounts_email`, `accounts_anonymous_identity`, `i18n_language`,
`i18n_translation_entry`.

### Каталог и версии игр

`catalog_genre`, `catalog_genre_translation`, `catalog_tag`,
`catalog_tag_translation`, `catalog_game`, `catalog_game_version`,
`catalog_game_translation`, `catalog_game_import_draft`,
`catalog_game_additional_genre`, `catalog_game_tag`, `catalog_game_asset`,
`i18n_game_locale_override`.

### Рейтинги, сессии, результаты и хранилище

`ratings_vote`, `ratings_aggregate`, `play_user_game_playtime`,
`gameplay_session`, `gameplay_result`, `leaderboards_entry`,
`gameplay_play_credit`, `gameplay_daily_stats`, `gameplay_storage`.

### Контент, SEO, аудит и эксплуатация

`content_page`, `content_page_translation`, `content_legal_document`,
`content_legal_document_version`, `content_user_legal_acceptance`,
`content_cookie_consent`, `content_seo_settings`, `content_redirect`,
`content_ad_slot`, `analytics_event`, `security_event`, `admin_audit_log`,
`moderation_action`, `moderation_report`, `crm_backup_run`,
`theme_token_set`, `theme_site_settings`.

## 4. Ключевые ограничения

### Game

- `technical_id` `UNIQUE`, regex `^[a-z][a-z0-9_]{1,38}[a-z0-9]$`.
- `host_label` `UNIQUE`, DNS-label regex, не начинается с `xn--`; список
  зарезервированных меток хранится в `theme_site_settings.reserved_host_labels`.
- `technical_id` и `host_label` защищены trigger `reject_game_identity_change`.
- `current_version_id` связан составным FK `(current_version_id,id) →
  catalog_game_version(id,game_id)`, то есть версия обязана принадлежать
  этой игре.
- `score_min_value <= score_max_value`; `min_session_seconds <=
  max_session_seconds`; status/score/unit/direction — CHECK.

### GameVersion

- `UNIQUE(game_id, semver)`.
- `UNIQUE(id, game_id)` — для составных FK.
- `reject_game_version_update` запрещает UPDATE; immutable.
- `package_hash`/`runtime_hash` — char(64); `manifest` — JSONB.
- `supported_languages` — JSONB; `claimed_verification` — CHECK.

### GameAsset

- `version_id` nullable; составной FK `(version_id,game_id) → 
  catalog_game_version(id,game_id)` гарантирует принадлежность версии игре.
- `type` — cover/screenshot; `alt` — JSONB per language.

### GameSession / GameResult

- `GameSession`: ровно один субъект (`user_id` xor `anon_id`); mode/state
  CHECK; `ticket_hash`; `credited_ms >= 0`; max 7 200 000 мс.
- `GameResult`: `session_id UNIQUE`; `game_id` добавлен для индексов §2.11.3;
  `UNIQUE(session_id,idempotency_key)`; `is_test`, quarantine, trust level.
- `LeaderboardEntry`: `UNIQUE(game_id,epoch,user_id)`, indexes по value
  в обе стороны.

### GameStorage

- `UNIQUE(game_id,subject_type,subject_id)`; `bytes <= 65536`;
  `subject_type ∈ {user,anon}`; `revision >= 1`.
- Глубина/число ключей JSONB проверяются сервисом/семантическим
  валидатором, не только БД.

### Событийные таблицы

- `analytics_event` — RANGE partition by `created_at`, PK `(id,created_at)`.
- `security_event`, `admin_audit_log`, `moderation_action` — BIGINT identity.
- Партиции создаются Celery/ops; TTL 90/365/730 дней соответственно
  (BA-PLAT-4.2 §2.18, §2.22).

## 5. Ограничения проектной схемы

1. SQL DDL **не применён** к основной БД; это проект для ревью. Для проверки
   синтаксиса он загружен в изолированную временную БД `ba_schema_check_002`
   (47 таблиц), после чего временная БД удалена; основная БД не менялась.
2. Глубина JSONB, число ключей, резервные host_label и часть business rules
   остаются в сервисном слое.
3. Полные Django-модели/миграции не создавались: это следующие этапы.
4. Точные политики партиционирования/retention требуют эксплуатационного
   решения.
5. `GameResult.game_id` — техническое дополнение для индексов §2.11.3; в
   тексте §2.22 поле не перечислено отдельно, но индекс §2.11.3 его требует.
