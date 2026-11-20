# App J — полный mapping полей manifest/catalog ↔ БД ↔ CRM

**Статус:** проектная таблица BA-FOUNDATION-002. Источник: BA-PLAT-4.2,
Приложение J. Не является реализацией импортёра/CRM-мастера.

Обозначения владельца: **P** — платформа (read-only CRM), **M** — импорт с
возможностью правки CRM, **C** — только CRM, **R** — расчётное.
`override` — можно ли зафиксировать ручное значение; `repeat` — поведение
повторного импорта.

| Источник | Поле пакета | Поле БД | Тип | Владелец | Override | Repeat/import | Immutable | Validation |
|---|---|---|---|---|---|---|---|---|
| manifest | `cartridge` | `GameVersion.manifest` | JSONB | P | нет | новая версия | версия immutable | const 1 |
| manifest | `protocol` | `GameVersion.manifest` | JSONB | P | нет | новая версия | версия immutable | const 1 |
| manifest | `id` | `Game.technical_id` | citext | P | нет | должен совпадать, иначе отказ | **да** | regex §2.4.1 |
| — | — | `Game.host_label` | citext | R | нет | никогда не меняется | **да** | DNS-label, reserved list |
| manifest | `version` | `GameVersion.semver` | varchar | P | нет | unique per game | версия immutable | semver, unique |
| manifest | `sdkVersion` | `GameVersion.sdk_version` | varchar | P | нет | проверка совместимости | версия immutable | semver-range |
| manifest | `entry` | `GameVersion.entry_path` | varchar | P | нет | только `index.html` | версия immutable | const |
| manifest | `name` | `GameTranslation.name` | varchar | M | да | fallback; приоритет catalog.name | нет | 1–128 |
| manifest | `genre` | `Game.primary_genre_id` | uuid FK | M | да | не затирать при overridden | нет | canonical genre |
| manifest | `tags` | `GameTag` M2M | M2M | M | да | новые теги создаются; overridden не затирать | нет | ≤8, code |
| manifest | `supportedLanguages` | `GameVersion.supported_languages` | JSONB | P | нет | покрытие пересчитывается | версия immutable | все языки в Language |
| manifest | `defaultLanguage` | `Game.default_language` | varchar | P | нет | — | нет | входит в supportedLanguages |
| manifest | `mobileSupport` | `Game.mobile_support` | boolean | M | да | — | нет | boolean |
| manifest | `orientation` | `Game.orientation` | varchar | M | да | — | нет | any/portrait/landscape |
| manifest | `estimatedPlayMinutes` | `Game.estimated_play_minutes` | smallint | M | да | — | нет | ≥1 |
| manifest | `theme.accent` | `Game.accent_color` | varchar(7) | M | да | — | нет | `#RRGGBB` |
| manifest | `score.type` | `Game.score_type` | varchar | P | нет | новая версия | нет | integer/number |
| manifest | `score.unit` | `Game.score_unit` | varchar | P | нет | новая версия | нет | points/ms/items/errors |
| manifest | `score.direction` | `Game.score_direction` | varchar | P | нет | смена → §2.11.4 | нет | higher/lower |
| manifest | `score.minValue` | `Game.score_min_value` | numeric | P | нет | — | нет | ≤ max |
| manifest | `score.maxValue` | `Game.score_max_value` | numeric | P | нет | — | нет | ≥ min, not null |
| manifest | `score.schemaVersion` | `Game.score_schema_version` | smallint | P | нет | смена → §2.11.4 | нет | ≥1 |
| manifest | `limits.minPlaytimeSeconds` | `Game.min_session_seconds` | integer | P | нет | — | нет | ≥5 |
| manifest | `limits.maxSessionSeconds` | `Game.max_session_seconds` | integer | P | нет | — | нет | 5–7200 |
| manifest | `limits.pauseOnBlur` | `Game.pause_on_blur` | boolean | P | нет | — | нет | boolean |
| manifest | `capabilities.*` | `Game.capabilities` | JSONB | P | нет | — | нет | externalOrigins=[], storage=sdk |
| manifest | `leaderboard.enabled` | `Game.leaderboard_enabled` | boolean | M | да | — | нет | boolean |
| manifest | `leaderboard.claimedVerification` | `GameVersion.claimed_verification` | varchar | P | нет | — | версия immutable | enum |
| manifest | `verification.profile` | `Game.verification_profile` | JSONB | P | нет | — | нет | maxPointsPerSecond/maxIdleGapMs |
| manifest | `verification.eventKinds/eventSchema` | `GameVersion.manifest` | JSONB | P | нет | обязательны при replay_verified | версия immutable | ≤32 kinds; schema 2020-12 |
| manifest | `assets.cover` | `GameAsset(type=cover)` | image/file | M | да | заменить, если не overridden | нет | 1280×720 |
| manifest | `assets.screenshots` | `GameAsset(type=screenshot)` | image/file | M | да | порядок из массива | нет | 2–4, 1280×720 |
| manifest | `assets.critical` | `GameVersion.critical_path_bytes_measured` | bigint | R | нет | пересчёт после SDK | версия immutable | ≤2 MiB gzip / ≤4 MiB отказ |
| manifest | `assets.criticalPathBytes` | `GameVersion.critical_path_bytes_declared` | bigint | P | нет | расхождение >10% warning | версия immutable | ≥0 |
| manifest | `credits` | `Game.credits`, `GameVersion.manifest` | JSONB | M | да | — | нет | author/license/aiGenerated |
| catalog | `name` | `GameTranslation.name` | varchar | M | да | conflict-diff | нет | ≤60? импорт; таблица 128 |
| catalog | `shortDescription` | `GameTranslation.short_description` | varchar | M | да | conflict-diff | нет | ≤120 |
| catalog | `description` | `GameTranslation.description` | text | M | да | conflict-diff | нет | 300–1600 |
| catalog | `instructions` | `GameTranslation.instructions` | text | M | да | conflict-diff | нет | ≤600 |
| catalog | `controls` | `GameTranslation.controls` | text | M | да | conflict-diff | нет | ≤400 |
| catalog | `seoTitle` | `SeoSettings.title` | varchar | M | да | conflict-diff | нет | ≤60 |
| catalog | `seoDescription` | `SeoSettings.description` | varchar | M | да | conflict-diff | нет | ≤160 |
| catalog | `coverAlt` | `GameAsset.alt[lang]` | JSONB | M | да | conflict-diff | нет | ≤160 |
| catalog | `screenshotAlts` | `GameAsset.alt[lang]` | JSONB | M | да | порядок/число должны совпасть | нет | count = screenshots |
| locales | `locales/*.json` | остаются в пакете | files | P | нет | GameLocaleOverride приоритетнее | нет | parity/keys |
| — | — | `Game.status`, `publish_at`, `published_at` | varchar/timestamptz | C | да | импорт не изменяет | нет | workflow |
| — | — | `rating_min_playtime_seconds`, `verifier_slug`, `trust_level_max`, `leaderboard_only_verified`, `leaderboard_epoch` | mixed | C | да | импорт не изменяет | epoch rules | CRM only |
| — | — | рейтинги, оценки, популярность, рекорды, статистика | R | R | нет | только платформа | нет | aggregate |
| — | — | `Game.slug`, `GameTranslation.slug`, подборки, дополнительные жанры | mixed | C | да | импорт предлагает | slug changes 301 | CRM approval |

## Полнота

Все строки Приложения J представлены: manifest, catalog, locales, CRM-only
поля, расчётные поля, ассеты, verification, score, limits, capabilities,
leaderboard, credits. Полный DDL — `docs/foundation/ba_schema.sql`.

## Открытые вопросы

- Точная максимальная длина `GameTranslation.name` (128 в текущей модели,
  60 в manifest; catalog name ≤60) — требует согласования.
- `GameResult.game_id` добавлен для индексов §2.11.3, хотя §2.22 перечисляет
  результат через `session_id`; это техническое дополнение.
- Импорт/CRM-мастер не реализуются на этапе 0.
