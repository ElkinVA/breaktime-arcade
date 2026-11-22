# Generated for ARCADE-P2-CRM-ROLES-001 (§2.16 roles).

from django.db import migrations, models


def backfill_superuser_owner(apps, schema_editor):
    """Preserve existing superuser CRM access as the owner role."""
    del schema_editor
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_superuser=True, is_staff=True).update(crm_role="owner")


def reverse_backfill_superuser_owner(apps, schema_editor):
    del schema_editor
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_superuser=True, is_staff=True, crm_role="owner").update(crm_role="")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_ownerrecoverycode_loginevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="crm_role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("owner", "Владелец"),
                    ("editor", "Редактор"),
                    ("moderator", "Модератор"),
                    ("observer", "Наблюдатель"),
                ],
                db_index=True,
                default="",
                help_text="Роль в CRM (§2.16); пустое значение — доступа нет.",
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_superuser_owner, reverse_backfill_superuser_owner),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=models.Q(("crm_role", ""))
                | (
                    models.Q(("is_staff", True))
                    & models.Q(
                        (
                            "crm_role__in",
                            ["owner", "editor", "moderator", "observer"],
                        )
                    )
                ),
                name="ck_user_crm_role_staff",
            ),
        ),
    ]
