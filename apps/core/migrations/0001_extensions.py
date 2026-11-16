from django.contrib.postgres.operations import CreateExtension
from django.db import migrations

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        CreateExtension("citext"),
        CreateExtension("pg_trgm"),
        CreateExtension("unaccent"),
    ]
