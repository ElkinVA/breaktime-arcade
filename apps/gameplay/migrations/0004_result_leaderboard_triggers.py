"""DB-002/DB-003: cross-table consistency for result and leaderboard.

Django cannot express these as composite FKs without hand-written SQL; the
triggers enforce the same invariants at the database boundary:

* a result's game/version must equal its session's game/version (DB-002);
* a leaderboard row's best_result must belong to the same game/epoch/user and
  carry the same value/achieved_at (DB-003).
"""

from django.db import migrations

RESULT_TRIGGER = """
CREATE OR REPLACE FUNCTION gameplay_result_session_consistency() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM gameplay_session s
        WHERE s.id = NEW.session_id
          AND s.game_id = NEW.game_id
          AND s.game_version_id = NEW.game_version_id
    ) THEN
        RAISE EXCEPTION 'gameplay_result session/game/version mismatch'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_gameplay_result_session_consistency ON gameplay_result;
CREATE TRIGGER trg_gameplay_result_session_consistency
BEFORE INSERT OR UPDATE ON gameplay_result
FOR EACH ROW EXECUTE FUNCTION gameplay_result_session_consistency();
"""

LEADERBOARD_TRIGGER = """
CREATE OR REPLACE FUNCTION gameplay_leaderboard_consistency() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM gameplay_result r
        WHERE r.id = NEW.best_result_id
          AND r.game_id = NEW.game_id
          AND r.epoch = NEW.epoch
          AND r.user_id = NEW.user_id
          AND r.value = NEW.value
          AND r.created_at = NEW.achieved_at
    ) THEN
        RAISE EXCEPTION 'gameplay_leaderboard_entry/result mismatch'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_gameplay_leaderboard_consistency ON gameplay_leaderboard_entry;
CREATE TRIGGER trg_gameplay_leaderboard_consistency
BEFORE INSERT OR UPDATE ON gameplay_leaderboard_entry
FOR EACH ROW EXECUTE FUNCTION gameplay_leaderboard_consistency();
"""

REVERSE = """
DROP TRIGGER IF EXISTS trg_gameplay_leaderboard_consistency ON gameplay_leaderboard_entry;
DROP FUNCTION IF EXISTS gameplay_leaderboard_consistency();
DROP TRIGGER IF EXISTS trg_gameplay_result_session_consistency ON gameplay_result;
DROP FUNCTION IF EXISTS gameplay_result_session_consistency();
"""


class Migration(migrations.Migration):
    dependencies = [("gameplay", "0003_gameresult_leaderboardentry_and_more")]

    operations = [
        migrations.RunSQL(RESULT_TRIGGER, REVERSE),
        migrations.RunSQL(LEADERBOARD_TRIGGER, REVERSE),
    ]
