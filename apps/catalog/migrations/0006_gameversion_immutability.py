from __future__ import annotations

from django.db import migrations

FORWARD = r"""
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

    IF (NEW.created_by IS DISTINCT FROM OLD.created_by AND NEW.created_by IS NOT NULL)
       OR (NEW.manual_review_by IS DISTINCT FROM OLD.manual_review_by
           AND NEW.manual_review_by IS NOT NULL)
    THEN
        RAISE EXCEPTION 'GameVersion audit references may only be nulled';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_game_version_immutable ON catalog_game_version;
CREATE TRIGGER trg_game_version_immutable
BEFORE UPDATE ON catalog_game_version
FOR EACH ROW EXECUTE FUNCTION ba_game_version_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS trg_game_version_immutable ON catalog_game_version;
DROP FUNCTION IF EXISTS ba_game_version_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_backfill_unaccent_search_vector"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
