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
                coalesce(name, '') || ' ' ||
                coalesce(short_description, '') || ' ' ||
                coalesce(description, '')
            )
            WHERE search_vector IS NULL
            """
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_gamegenre_game_additional_genres_gametag_game_tags_and_more"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
