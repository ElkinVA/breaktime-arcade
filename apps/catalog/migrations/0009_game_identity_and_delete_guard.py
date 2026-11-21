from __future__ import annotations

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION ba_game_identity_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.published_at IS NOT NULL OR OLD.status IN ('published', 'hidden', 'archived'))
       AND (NEW.technical_id IS DISTINCT FROM OLD.technical_id
            OR NEW.host_label IS DISTINCT FROM OLD.host_label)
    THEN
        RAISE EXCEPTION 'Game identity is immutable after publication';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_game_identity_immutable ON catalog_game;
CREATE TRIGGER trg_game_identity_immutable
BEFORE UPDATE ON catalog_game
FOR EACH ROW EXECUTE FUNCTION ba_game_identity_immutable();

CREATE OR REPLACE FUNCTION ba_game_delete_forbidden()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Game rows are never physically deleted';
END;
$$;

DROP TRIGGER IF EXISTS trg_game_delete_forbidden ON catalog_game;
CREATE TRIGGER trg_game_delete_forbidden
BEFORE DELETE ON catalog_game
FOR EACH ROW EXECUTE FUNCTION ba_game_delete_forbidden();
"""

REVERSE = """
DROP TRIGGER IF EXISTS trg_game_delete_forbidden ON catalog_game;
DROP FUNCTION IF EXISTS ba_game_delete_forbidden();
DROP TRIGGER IF EXISTS trg_game_identity_immutable ON catalog_game;
DROP FUNCTION IF EXISTS ba_game_identity_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0008_alter_gametranslation_name"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
