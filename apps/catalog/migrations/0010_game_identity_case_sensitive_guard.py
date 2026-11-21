from __future__ import annotations

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION ba_game_identity_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.published_at IS NOT NULL OR OLD.status IN ('published', 'hidden', 'archived'))
       AND (NEW.technical_id::text IS DISTINCT FROM OLD.technical_id::text
            OR NEW.host_label::text IS DISTINCT FROM OLD.host_label::text)
    THEN
        RAISE EXCEPTION 'Game identity is immutable after publication';
    END IF;
    RETURN NEW;
END;
$$;
"""

REVERSE = r"""
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
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_game_identity_and_delete_guard"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
