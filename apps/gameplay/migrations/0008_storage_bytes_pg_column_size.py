"""Align the DB byte counter with the service quota.

``jsonb::text`` adds spaces and reorders keys, so a canonical document that
passes the 64 KiB service check could trip the trigger. ``pg_column_size`` is
the binary JSONB size (never larger), leaving the service as the binding
UTF-8 quota while the DB remains a safety net.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION gameplay_storage_compute_bytes() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.bytes := pg_column_size(NEW.data);
    IF NEW.bytes > 65536 THEN
        RAISE EXCEPTION 'gameplay_storage quota exceeded'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
"""

REVERSE = """
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
"""


class Migration(migrations.Migration):
    dependencies = [("gameplay", "0007_storage_bytes_trigger")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
