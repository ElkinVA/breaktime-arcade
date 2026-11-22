# Generated for ARCADE-P2-CRM-ROLES-001 (§2.16.1 audit trail).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("crm", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdminAuditLog",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("staff.role_changed", "Смена роли сотрудника"),
                            ("staff.activated", "Активация сотрудника"),
                            ("staff.deactivated", "Деактивация сотрудника"),
                            ("game.published", "Публикация версии"),
                            ("game.rolled_back", "Откат версии"),
                        ],
                        max_length=64,
                    ),
                ),
                ("object_type", models.CharField(blank=True, max_length=64)),
                ("object_id", models.UUIDField(blank=True, null=True)),
                ("before_data", models.JSONField(blank=True, null=True)),
                ("after_data", models.JSONField(blank=True, null=True)),
                ("reason", models.TextField(blank=True)),
                ("ip_hash", models.CharField(blank=True, max_length=64)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="crm_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Запись аудита CRM",
                "verbose_name_plural": "Журнал аудита CRM",
                "db_table": "admin_audit_log",
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["action", "created_at"],
                        name="ix_audit_action_created",
                    ),
                    models.Index(
                        fields=["object_type", "object_id"],
                        name="ix_audit_object",
                    ),
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION ba_admin_audit_immutable()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $ba_audit$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'admin_audit_log is append-only';
                END IF;
                IF NEW.id = OLD.id
                   AND NEW.created_at = OLD.created_at
                   AND NEW.action IS NOT DISTINCT FROM OLD.action
                   AND NEW.object_type IS NOT DISTINCT FROM OLD.object_type
                   AND NEW.object_id IS NOT DISTINCT FROM OLD.object_id
                   AND NEW.before_data IS NOT DISTINCT FROM OLD.before_data
                   AND NEW.after_data IS NOT DISTINCT FROM OLD.after_data
                   AND NEW.reason IS NOT DISTINCT FROM OLD.reason
                   AND NEW.ip_hash IS NOT DISTINCT FROM OLD.ip_hash
                   AND NEW.actor_id IS NULL
                   AND OLD.actor_id IS NOT NULL
                THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'admin_audit_log is append-only';
            END;
            $ba_audit$;
            """,
            reverse_sql="DROP FUNCTION IF EXISTS ba_admin_audit_immutable();",
        ),
        migrations.RunSQL(
            sql="""
            CREATE TRIGGER ba_admin_audit_immutable
            BEFORE UPDATE OR DELETE ON admin_audit_log
            FOR EACH ROW EXECUTE FUNCTION ba_admin_audit_immutable();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS ba_admin_audit_immutable ON admin_audit_log;",
        ),
    ]
