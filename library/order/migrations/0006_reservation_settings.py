from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def seed_policy(apps, schema_editor):
    apps.get_model("order", "ReservationSettings").objects.using(
        schema_editor.connection.alias
    ).get_or_create(pk=1, defaults={"hours": 48})


class Migration(migrations.Migration):
    dependencies = [("order", "0005_keep_records_of_deleted_readers")]

    operations = [
        migrations.CreateModel(
            name="ReservationSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("hours", models.PositiveSmallIntegerField(default=48, validators=[MinValueValidator(1), MaxValueValidator(168)])),
            ],
            options={"constraints": [
                models.CheckConstraint(condition=models.Q(pk=1), name="one_reservation_settings"),
                models.CheckConstraint(condition=models.Q(hours__gte=1, hours__lte=168), name="reservation_hours_in_range"),
            ]},
        ),
        migrations.RunPython(seed_policy, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="reservation", name="reservation_lasts_48_hours"),
        migrations.AddConstraint(
            model_name="reservation",
            constraint=models.CheckConstraint(condition=models.Q(expires_at__gt=models.F("created_at")), name="reservation_deadline_after_creation"),
        ),
    ]
