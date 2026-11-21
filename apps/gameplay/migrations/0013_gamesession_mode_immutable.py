from __future__ import annotations

from django.db import migrations

FORWARD = r"""
CREATE OR REPLACE FUNCTION ba_game_session_mode_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.mode IS DISTINCT FROM OLD.mode THEN
        RAISE EXCEPTION 'GameSession.mode is immutable';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_game_session_mode_immutable ON gameplay_session;
CREATE TRIGGER trg_game_session_mode_immutable
BEFORE UPDATE ON gameplay_session
FOR EACH ROW EXECUTE FUNCTION ba_game_session_mode_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS trg_game_session_mode_immutable ON gameplay_session;
DROP FUNCTION IF EXISTS ba_game_session_mode_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("gameplay", "0012_gamesession_ck_gameplay_session_mode_subject"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
