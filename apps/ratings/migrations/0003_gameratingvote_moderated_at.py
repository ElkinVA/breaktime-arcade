from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ratings", "0002_gameratingvote_ix_ratings_vote_user_changed"),
    ]

    operations = [
        migrations.AddField(
            model_name="gameratingvote",
            name="moderated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
