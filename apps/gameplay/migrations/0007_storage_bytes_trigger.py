"""DB-008: storage bytes are computed from the JSON text and capped at 64 KiB."""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION gameplay_storage_compute_bytes() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.bytes := octet_length(NEW.data::text);
    IF NEW.bytes > 65536 THEN
        RAISE EXCEPTION 'gameplay_storage quota exceeded'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_gameplay_storage_bytes ON gameplay_storage;
CREATE TRIGGER trg_gameplay_storage_bytes
BEFORE INSERT OR UPDATE ON gameplay_storage
FOR EACH ROW EXECUTE FUNCTION gameplay_storage_compute_bytes();
"""

REVERSE = """
DROP TRIGGER IF EXISTS trg_gameplay_storage_bytes ON gameplay_storage;
DROP FUNCTION IF EXISTS gameplay_storage_compute_bytes();
"""


class Migration(migrations.Migration):
    dependencies = [("gameplay", "0006_gamestorage")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
