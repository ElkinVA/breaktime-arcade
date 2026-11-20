from django.db import migrations


def backfill(apps: object, schema_editor: object) -> None:
    del apps, schema_editor
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE catalog_game_translation
            SET search_vector = to_tsvector(
                'simple',
                unaccent(
                    coalesce(name, '') || ' ' ||
                    coalesce(short_description, '') || ' ' ||
                    coalesce(description, '')
                )
            )
            """
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_backfill_search_vector"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
