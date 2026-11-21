-- BA-FOUNDATION-002 — ПРОЕКТНАЯ схема данных BA-PLAT-4.2 §2.22.
-- СТАТУС: DRAFT / DESIGN ONLY. Не применять как миграцию.
-- Нормативный источник: technical_specification/ts_site.txt §2.22.
-- Здесь нет секретов и значений окружения.

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- UUIDv7: в PostgreSQL 18 используется встроенная функция uuidv7().
-- Для обычных сущностей: uuid PRIMARY KEY DEFAULT uuidv7().
-- Для событийных таблиц: BIGINT GENERATED ALWAYS AS IDENTITY.

CREATE TABLE accounts_user (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    login citext NOT NULL UNIQUE,
    password text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    is_staff boolean NOT NULL DEFAULT false,
    totp_secret text,
    totp_confirmed_at timestamptz,
    last_login timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_user_login CHECK (login::text ~ '^[a-z0-9_.-]{3,30}$')
);

CREATE TABLE accounts_recovery_code (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    user_id uuid NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    code_hash text NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_recovery_user_active ON accounts_recovery_code(user_id) WHERE used_at IS NULL;

CREATE TABLE accounts_profile (
    user_id uuid PRIMARY KEY REFERENCES accounts_user(id) ON DELETE CASCADE,
    nickname citext NOT NULL UNIQUE,
    nickname_skeleton text NOT NULL UNIQUE,
    language_id uuid,
    theme text NOT NULL DEFAULT 'dark',
    age_confirmed_at timestamptz,
    marketing_consent_at timestamptz,
    deletion_requested_at timestamptz,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE accounts_nickname_history (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    user_id uuid NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    nickname citext,
    nickname_skeleton text NOT NULL,
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_to timestamptz,
    CONSTRAINT ck_nickname_history_period CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX ix_nickname_history_user ON accounts_nickname_history(user_id, valid_from);

CREATE TABLE accounts_nickname_reservation (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    skeleton_hmac text NOT NULL UNIQUE,
    reserved_until timestamptz NOT NULL,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE accounts_email (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    user_id uuid NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    email citext NOT NULL UNIQUE,
    verified_at timestamptz,
    is_primary boolean NOT NULL DEFAULT false,
    bounce_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_email_user_v1 UNIQUE (user_id)
);

CREATE TABLE accounts_anonymous_identity (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX ix_anonymous_expiry ON accounts_anonymous_identity(expires_at);

CREATE TABLE i18n_language (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    code citext NOT NULL UNIQUE,
    name varchar(64) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    is_rtl boolean NOT NULL DEFAULT false,
    sort_order smallint NOT NULL DEFAULT 0,
    plural_rule varchar(16) NOT NULL DEFAULT 'other',
    fts_config varchar(64) NOT NULL DEFAULT '',
    ui_ready_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_language_active_order ON i18n_language(is_active, sort_order, code);

ALTER TABLE accounts_profile
    ADD CONSTRAINT fk_profile_language
    FOREIGN KEY (language_id) REFERENCES i18n_language(id) ON DELETE SET NULL;

CREATE TABLE i18n_translation_entry (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    namespace varchar(64) NOT NULL,
    key varchar(128) NOT NULL,
    language_id uuid NOT NULL REFERENCES i18n_language(id) ON DELETE CASCADE,
    value text NOT NULL DEFAULT '',
    status varchar(16) NOT NULL DEFAULT 'draft',
    updated_by uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_translation_key UNIQUE (namespace, key, language_id),
    CONSTRAINT ck_translation_status CHECK (status IN ('missing','draft','review','verified','published'))
);

CREATE TABLE catalog_genre (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    code citext NOT NULL UNIQUE,
    sort_order smallint NOT NULL DEFAULT 0,
    image text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE catalog_genre_translation (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    genre_id uuid NOT NULL REFERENCES catalog_genre(id) ON DELETE CASCADE,
    language_id uuid NOT NULL REFERENCES i18n_language(id) ON DELETE CASCADE,
    name varchar(64) NOT NULL,
    slug citext NOT NULL,
    description text NOT NULL DEFAULT '',
    seo_title varchar(60) NOT NULL DEFAULT '',
    seo_description varchar(160) NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_genre_translation UNIQUE (genre_id, language_id),
    CONSTRAINT uq_genre_slug_lang UNIQUE (language_id, slug)
);

CREATE TABLE catalog_tag (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    code citext NOT NULL UNIQUE,
    needs_translation boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE catalog_tag_translation (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    tag_id uuid NOT NULL REFERENCES catalog_tag(id) ON DELETE CASCADE,
    language_id uuid NOT NULL REFERENCES i18n_language(id) ON DELETE CASCADE,
    name varchar(64) NOT NULL,
    slug citext NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_tag_translation UNIQUE (tag_id, language_id),
    CONSTRAINT uq_tag_slug_lang UNIQUE (language_id, slug)
);

CREATE TABLE catalog_game (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    technical_id citext NOT NULL UNIQUE,
    host_label citext NOT NULL UNIQUE,
    slug citext NOT NULL UNIQUE,
    primary_genre_id uuid NOT NULL REFERENCES catalog_genre(id) ON DELETE RESTRICT,
    status varchar(16) NOT NULL DEFAULT 'draft',
    current_version_id uuid,
    published_at timestamptz,
    publish_at timestamptz,
    rating_min_playtime_seconds integer NOT NULL DEFAULT 120,
    min_session_seconds integer NOT NULL DEFAULT 15,
    max_session_seconds integer NOT NULL DEFAULT 1800,
    pause_on_blur boolean NOT NULL DEFAULT true,
    mobile_support boolean NOT NULL DEFAULT true,
    orientation varchar(16) NOT NULL DEFAULT 'any',
    estimated_play_minutes smallint NOT NULL DEFAULT 5,
    default_language varchar(8) NOT NULL DEFAULT 'en',
    accent_color varchar(7) NOT NULL DEFAULT '#39ff88',
    capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
    verification_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
    score_type varchar(16) NOT NULL DEFAULT 'integer',
    score_unit varchar(16) NOT NULL DEFAULT 'points',
    score_direction varchar(16) NOT NULL DEFAULT 'higher_is_better',
    score_min_value numeric(20,4) NOT NULL DEFAULT 0,
    score_max_value numeric(20,4) NOT NULL DEFAULT 100000,
    score_schema_version smallint NOT NULL DEFAULT 1,
    leaderboard_epoch integer NOT NULL DEFAULT 1,
    overridden_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    credits jsonb NOT NULL DEFAULT '[]'::jsonb,
    trust_level_max varchar(32) NOT NULL DEFAULT 'heuristic_validated',
    verifier_slug varchar(64),
    leaderboard_enabled boolean NOT NULL DEFAULT true,
    leaderboard_only_verified boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_game_technical_id CHECK (technical_id::text ~ '^[a-z][a-z0-9_]{1,38}[a-z0-9]$'),
    CONSTRAINT ck_game_host_label CHECK (host_label::text ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$' AND host_label::text !~ '^xn--'),
    CONSTRAINT ck_game_status CHECK (status IN ('draft','review','published','hidden','archived')),
    CONSTRAINT ck_game_score_range CHECK (score_min_value <= score_max_value),
    CONSTRAINT ck_game_session_range CHECK (min_session_seconds <= max_session_seconds),
    CONSTRAINT ck_game_accent CHECK (accent_color ~ '^#[0-9A-Fa-f]{6}$')
);

CREATE TABLE catalog_game_version (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    semver varchar(32) NOT NULL,
    package_hash char(64) NOT NULL,
    runtime_hash char(64) NOT NULL,
    sdk_version varchar(32) NOT NULL,
    sdk_contract_version varchar(32) NOT NULL DEFAULT '1',
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    manifest jsonb NOT NULL,
    entry_path varchar(255) NOT NULL DEFAULT 'index.html',
    critical_path_bytes_declared bigint CHECK (critical_path_bytes_declared >= 0),
    critical_path_bytes_measured bigint CHECK (critical_path_bytes_measured >= 0),
    supported_languages jsonb NOT NULL DEFAULT '[]'::jsonb,
    claimed_verification varchar(32) NOT NULL DEFAULT 'client_reported',
    validation_report jsonb NOT NULL DEFAULT '{}'::jsonb,
    import_report jsonb NOT NULL DEFAULT '{}'::jsonb,
    injection_report jsonb NOT NULL DEFAULT '{}'::jsonb,
    e2e_report jsonb NOT NULL DEFAULT '{}'::jsonb,
    manual_review_by uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    manual_review_at timestamptz,
    created_by uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_game_version_semver UNIQUE (game_id, semver),
    CONSTRAINT uq_game_version_identity UNIQUE (id, game_id),
    CONSTRAINT ck_game_version_verification CHECK (claimed_verification IN ('client_reported','heuristic_validated','replay_verified'))
);

ALTER TABLE catalog_game
    ADD CONSTRAINT fk_game_current_version
    FOREIGN KEY (current_version_id, id)
    REFERENCES catalog_game_version(id, game_id)
    ON DELETE RESTRICT;

CREATE TABLE catalog_game_translation (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    language_id uuid NOT NULL REFERENCES i18n_language(id) ON DELETE CASCADE,
    name varchar(128) NOT NULL,
    slug citext NOT NULL,
    short_description varchar(160) NOT NULL DEFAULT '',
    description text NOT NULL DEFAULT '',
    instructions text NOT NULL DEFAULT '',
    controls text NOT NULL DEFAULT '',
    seo_title varchar(60) NOT NULL DEFAULT '',
    seo_description varchar(160) NOT NULL DEFAULT '',
    search_vector tsvector,
    overridden_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_game_translation UNIQUE (game_id, language_id),
    CONSTRAINT uq_game_translation_slug UNIQUE (language_id, slug)
);
CREATE INDEX ix_game_translation_search ON catalog_game_translation USING gin(search_vector);

CREATE TABLE catalog_game_import_draft (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    author_id uuid NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    game_id uuid REFERENCES catalog_game(id) ON DELETE SET NULL,
    step smallint NOT NULL DEFAULT 1,
    package_hash char(64) NOT NULL,
    uploaded_file text NOT NULL,
    parsed_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    parsed_catalog jsonb NOT NULL DEFAULT '{}'::jsonb,
    decisions jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation_report jsonb NOT NULL DEFAULT '{}'::jsonb,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_import_draft_step CHECK (step BETWEEN 1 AND 5)
);

CREATE TABLE catalog_game_additional_genre (
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    genre_id uuid NOT NULL REFERENCES catalog_genre(id) ON DELETE CASCADE,
    PRIMARY KEY (game_id, genre_id)
);

CREATE TABLE catalog_game_tag (
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    tag_id uuid NOT NULL REFERENCES catalog_tag(id) ON DELETE CASCADE,
    PRIMARY KEY (game_id, tag_id)
);

CREATE TABLE catalog_game_asset (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    version_id uuid,
    type varchar(16) NOT NULL,
    file text NOT NULL,
    alt jsonb NOT NULL DEFAULT '{}'::jsonb,
    sort_order smallint NOT NULL DEFAULT 0,
    width integer CHECK (width > 0),
    height integer CHECK (height > 0),
    bytes bigint CHECK (bytes >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_asset_type CHECK (type IN ('cover','screenshot')),
    CONSTRAINT fk_asset_version_same_game
        FOREIGN KEY (version_id, game_id)
        REFERENCES catalog_game_version(id, game_id)
        ON DELETE RESTRICT
);

CREATE TABLE i18n_game_locale_override (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    language_id uuid NOT NULL REFERENCES i18n_language(id) ON DELETE CASCADE,
    key varchar(128) NOT NULL,
    value text NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'draft',
    updated_by uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_game_override UNIQUE (game_id, language_id, key)
);

CREATE TABLE ratings_vote (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    value smallint NOT NULL,
    is_valid boolean NOT NULL DEFAULT true,
    moderated_by uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    reason text,
    changed_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_rating_game_user UNIQUE (game_id, user_id),
    CONSTRAINT ck_rating_value CHECK (value BETWEEN 1 AND 5)
);

CREATE TABLE ratings_aggregate (
    game_id uuid PRIMARY KEY REFERENCES catalog_game(id) ON DELETE CASCADE,
    sum_value bigint NOT NULL DEFAULT 0 CHECK (sum_value >= 0),
    vote_count bigint NOT NULL DEFAULT 0 CHECK (vote_count >= 0),
    avg_value numeric(4,2) NOT NULL DEFAULT 0,
    wr_score numeric(8,4) NOT NULL DEFAULT 0,
    distribution jsonb NOT NULL DEFAULT '{}'::jsonb,
    recalculated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE play_user_game_playtime (
    user_id uuid NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    verified_seconds bigint NOT NULL DEFAULT 0 CHECK (verified_seconds >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, game_id)
);

CREATE TABLE gameplay_session (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    game_version_id uuid NOT NULL,
    user_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    anon_id uuid REFERENCES accounts_anonymous_identity(id) ON DELETE SET NULL,
    mode varchar(16) NOT NULL,
    state varchar(16) NOT NULL DEFAULT 'created',
    ticket_hash text NOT NULL,
    ticket_expires_at timestamptz NOT NULL,
    binding_nonce_hash text,
    activated_at timestamptz,
    finished_at timestamptz,
    last_heartbeat_at timestamptz,
    credited_ms bigint NOT NULL DEFAULT 0 CHECK (credited_ms >= 0),
    ip_hash char(64),
    ua_hash char(64),
    seed text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_session_version_same_game
        FOREIGN KEY (game_version_id, game_id)
        REFERENCES catalog_game_version(id, game_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_session_subject CHECK ((user_id IS NULL) <> (anon_id IS NULL)),
    CONSTRAINT ck_session_mode CHECK (mode IN ('user','guest','preview','autotest')),
    CONSTRAINT ck_session_state CHECK (state IN ('created','active','finished','expired','aborted')),
    CONSTRAINT ck_session_credited CHECK (credited_ms <= 7200000)
);
CREATE INDEX ix_session_game_active ON gameplay_session(game_id, state, last_heartbeat_at);

CREATE TABLE gameplay_result (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    session_id uuid NOT NULL UNIQUE REFERENCES gameplay_session(id) ON DELETE CASCADE,
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    user_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    anon_id uuid REFERENCES accounts_anonymous_identity(id) ON DELETE SET NULL,
    epoch integer NOT NULL,
    value numeric(20,4) NOT NULL,
    unit varchar(16) NOT NULL,
    duration_ms bigint NOT NULL CHECK (duration_ms >= 0),
    trust_level varchar(32) NOT NULL,
    is_public boolean NOT NULL DEFAULT false,
    is_quarantined boolean NOT NULL DEFAULT false,
    is_test boolean NOT NULL DEFAULT false,
    idempotency_key uuid NOT NULL,
    verifier_flags jsonb NOT NULL DEFAULT '{}'::jsonb,
    achieved_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_result_subject CHECK ((user_id IS NULL) <> (anon_id IS NULL)),
    CONSTRAINT uq_result_idempotency UNIQUE (session_id, idempotency_key),
    CONSTRAINT ck_result_trust CHECK (trust_level IN ('client_reported','heuristic_validated','replay_verified','server_authoritative'))
);
CREATE INDEX ix_result_best_higher ON gameplay_result(game_id, user_id, value DESC, achieved_at ASC)
    WHERE is_public AND NOT is_quarantined AND NOT is_test;
CREATE INDEX ix_result_best_lower ON gameplay_result(game_id, user_id, value ASC, achieved_at ASC)
    WHERE is_public AND NOT is_quarantined AND NOT is_test;

CREATE TABLE leaderboards_entry (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    epoch integer NOT NULL,
    user_id uuid NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    best_result_id uuid NOT NULL REFERENCES gameplay_result(id) ON DELETE CASCADE,
    value numeric(20,4) NOT NULL,
    achieved_at timestamptz NOT NULL,
    is_public boolean NOT NULL DEFAULT true,
    trust_level varchar(32) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_leaderboard_user UNIQUE (game_id, epoch, user_id)
);
CREATE INDEX ix_leaderboard_higher ON leaderboards_entry(game_id, epoch, value DESC, achieved_at ASC) WHERE is_public;
CREATE INDEX ix_leaderboard_lower ON leaderboards_entry(game_id, epoch, value ASC, achieved_at ASC) WHERE is_public;

CREATE TABLE gameplay_play_credit (
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    subject_type varchar(16) NOT NULL,
    subject_id uuid NOT NULL,
    last_credited_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, subject_type, subject_id),
    CONSTRAINT ck_play_credit_subject CHECK (subject_type IN ('user','anon'))
);

CREATE TABLE gameplay_daily_stats (
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    date date NOT NULL,
    sessions bigint NOT NULL DEFAULT 0 CHECK (sessions >= 0),
    unique_sessions bigint NOT NULL DEFAULT 0 CHECK (unique_sessions >= 0),
    completions bigint NOT NULL DEFAULT 0 CHECK (completions >= 0),
    avg_duration numeric(12,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (game_id, date)
);

CREATE TABLE gameplay_storage (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    game_id uuid NOT NULL REFERENCES catalog_game(id) ON DELETE CASCADE,
    subject_type varchar(16) NOT NULL,
    subject_id uuid NOT NULL,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    bytes integer NOT NULL DEFAULT 0,
    revision bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    CONSTRAINT uq_storage_subject UNIQUE (game_id, subject_type, subject_id),
    CONSTRAINT ck_storage_subject CHECK (subject_type IN ('user','anon')),
    CONSTRAINT ck_storage_bytes CHECK (bytes >= 0 AND bytes <= 65536),
    CONSTRAINT ck_storage_revision CHECK (revision >= 1)
);

CREATE TABLE content_page (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    slug citext NOT NULL UNIQUE,
    is_published boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE content_page_translation (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    page_id uuid NOT NULL REFERENCES content_page(id) ON DELETE CASCADE,
    language_id uuid NOT NULL REFERENCES i18n_language(id) ON DELETE CASCADE,
    title varchar(200) NOT NULL,
    body text NOT NULL DEFAULT '',
    seo_title varchar(60) NOT NULL DEFAULT '',
    seo_description varchar(160) NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_page_translation UNIQUE (page_id, language_id)
);

CREATE TABLE content_legal_document (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    code citext NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE content_legal_document_version (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    document_id uuid NOT NULL REFERENCES content_legal_document(id) ON DELETE CASCADE,
    version varchar(32) NOT NULL,
    language_id uuid NOT NULL REFERENCES i18n_language(id) ON DELETE CASCADE,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_legal_version_language UNIQUE (document_id, version, language_id)
);

CREATE TABLE content_user_legal_acceptance (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    user_id uuid NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    version_id uuid NOT NULL REFERENCES content_legal_document_version(id) ON DELETE CASCADE,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    ip_hash char(64),
    CONSTRAINT uq_user_legal_version UNIQUE (user_id, version_id)
);

CREATE TABLE content_cookie_consent (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    user_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    anon_id uuid REFERENCES accounts_anonymous_identity(id) ON DELETE SET NULL,
    categories jsonb NOT NULL DEFAULT '{}'::jsonb,
    version varchar(32) NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    ip_hash char(64),
    CONSTRAINT ck_cookie_subject CHECK ((user_id IS NULL) <> (anon_id IS NULL))
);

CREATE TABLE content_seo_settings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    object_type varchar(32) NOT NULL,
    object_id uuid NOT NULL,
    title varchar(60) NOT NULL DEFAULT '',
    description varchar(160) NOT NULL DEFAULT '',
    og_image text,
    noindex boolean NOT NULL DEFAULT false,
    canonical_override text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_seo_object UNIQUE (object_type, object_id)
);

CREATE TABLE content_redirect (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    from_path text NOT NULL UNIQUE,
    to_path text NOT NULL,
    code smallint NOT NULL DEFAULT 301,
    hits bigint NOT NULL DEFAULT 0 CHECK (hits >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_redirect_code CHECK (code IN (301,302))
);

CREATE TABLE content_ad_slot (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    code citext NOT NULL UNIQUE,
    position varchar(32) NOT NULL,
    sizes jsonb NOT NULL DEFAULT '[]'::jsonb,
    devices jsonb NOT NULL DEFAULT '[]'::jsonb,
    starts_at timestamptz,
    ends_at timestamptz,
    is_enabled boolean NOT NULL DEFAULT false,
    provider_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analytics_event (
    id bigint GENERATED ALWAYS AS IDENTITY,
    created_at timestamptz NOT NULL DEFAULT now(),
    event_type varchar(64) NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE security_event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    event_type varchar(64) NOT NULL,
    severity varchar(16) NOT NULL,
    actor_type varchar(16),
    actor_id uuid,
    ip_hash char(64),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_security_severity CHECK (severity IN ('info','warning','critical'))
);
CREATE INDEX ix_security_created ON security_event(created_at);

CREATE TABLE admin_audit_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    actor_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    action varchar(64) NOT NULL,
    object_type varchar(64),
    object_id uuid,
    before_data jsonb,
    after_data jsonb,
    reason text,
    ip_hash char(64)
);
CREATE INDEX ix_audit_created ON admin_audit_log(created_at);

CREATE TABLE moderation_action (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    object_type varchar(64) NOT NULL,
    object_id uuid NOT NULL,
    decision varchar(32) NOT NULL,
    reason text NOT NULL,
    operator_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL
);

CREATE TABLE moderation_report (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    object_type varchar(64) NOT NULL,
    object_id uuid NOT NULL,
    reporter_user_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    reporter_anon_id uuid REFERENCES accounts_anonymous_identity(id) ON DELETE SET NULL,
    category varchar(64) NOT NULL,
    text text NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'new',
    resolution text,
    handled_by uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_report_status CHECK (status IN ('new','review','resolved','rejected'))
);

CREATE TABLE crm_backup_run (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    type varchar(16) NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status varchar(16) NOT NULL DEFAULT 'running',
    size_bytes bigint CHECK (size_bytes >= 0),
    verified_at timestamptz,
    meta jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_backup_type CHECK (type IN ('full','wal','restore_check')),
    CONSTRAINT ck_backup_status CHECK (status IN ('running','success','failed'))
);

CREATE TABLE theme_token_set (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    version integer NOT NULL,
    tokens jsonb NOT NULL,
    hash char(16) NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT false,
    updated_by uuid REFERENCES accounts_user(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_theme_single_active ON theme_token_set(is_active) WHERE is_active;

CREATE TABLE theme_site_settings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    logo text,
    favicon text,
    contacts jsonb NOT NULL DEFAULT '{}'::jsonb,
    counter_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    default_theme varchar(16) NOT NULL DEFAULT 'dark',
    reserved_host_labels jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Immutability triggers (§2.4.1, §2.14.1).
CREATE OR REPLACE FUNCTION reject_game_identity_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.technical_id IS DISTINCT FROM OLD.technical_id
       OR NEW.host_label IS DISTINCT FROM OLD.host_label THEN
        RAISE EXCEPTION 'Game.technical_id and host_label are immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_game_identity_immutable
BEFORE UPDATE ON catalog_game
FOR EACH ROW EXECUTE FUNCTION reject_game_identity_change();

CREATE OR REPLACE FUNCTION ba_game_version_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.game_id IS DISTINCT FROM OLD.game_id
       OR NEW.semver IS DISTINCT FROM OLD.semver
       OR NEW.package_hash IS DISTINCT FROM OLD.package_hash
       OR NEW.runtime_hash IS DISTINCT FROM OLD.runtime_hash
       OR NEW.sdk_version IS DISTINCT FROM OLD.sdk_version
       OR NEW.sdk_contract_version IS DISTINCT FROM OLD.sdk_contract_version
       OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes
       OR NEW.manifest IS DISTINCT FROM OLD.manifest
       OR NEW.entry_path IS DISTINCT FROM OLD.entry_path
       OR NEW.critical_path_bytes_declared IS DISTINCT FROM OLD.critical_path_bytes_declared
       OR NEW.critical_path_bytes_measured IS DISTINCT FROM OLD.critical_path_bytes_measured
       OR NEW.supported_languages IS DISTINCT FROM OLD.supported_languages
       OR NEW.claimed_verification IS DISTINCT FROM OLD.claimed_verification
       OR NEW.validation_report IS DISTINCT FROM OLD.validation_report
       OR NEW.import_report IS DISTINCT FROM OLD.import_report
       OR NEW.injection_report IS DISTINCT FROM OLD.injection_report
       OR NEW.e2e_report IS DISTINCT FROM OLD.e2e_report
       OR NEW.manual_review_at IS DISTINCT FROM OLD.manual_review_at
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'GameVersion content is immutable';
    END IF;

    IF (NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
        AND NEW.created_by_id IS NOT NULL)
       OR (NEW.manual_review_by_id IS DISTINCT FROM OLD.manual_review_by_id
           AND NEW.manual_review_by_id IS NOT NULL)
    THEN
        RAISE EXCEPTION 'GameVersion audit references may only be nulled';
    END IF;

    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_game_version_immutable
BEFORE UPDATE ON catalog_game_version
FOR EACH ROW EXECUTE FUNCTION ba_game_version_immutable();

-- Application-level notes:
-- * analytics_event partitions must be created ahead (e.g. monthly) and old
--   partitions detached/dropped after 90 days.
-- * GameStorage JSON depth/key count are enforced by the service/semantic
--   validator; the DB only enforces byte quota.
-- * Reserved host labels are stored in theme_site_settings and validated by
--   the import service.
