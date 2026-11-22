from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0002_adminauditlog"),
    ]

    operations = [
        migrations.AlterField(
            model_name="adminauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("staff.role_changed", "Смена роли сотрудника"),
                    ("staff.activated", "Активация сотрудника"),
                    ("staff.deactivated", "Деактивация сотрудника"),
                    ("game.published", "Публикация версии"),
                    ("game.rolled_back", "Откат версии"),
                    ("rating.hidden", "Скрытие оценки"),
                    ("rating.restored", "Восстановление оценки"),
                    ("complaint.assigned", "Назначение жалобы"),
                    ("complaint.resolved", "Решение по жалобе"),
                    ("complaint.rejected", "Отклонение жалобы"),
                ],
                max_length=64,
            ),
        ),
    ]
