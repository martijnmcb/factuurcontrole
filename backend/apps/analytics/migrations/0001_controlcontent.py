from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ControlContent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("control_id", models.IntegerField()),
                (
                    "soortvervoer",
                    models.CharField(
                        blank=True,
                        choices=[("", "Algemeen"), ("RG", "RG"), ("VA", "VA")],
                        default="",
                        max_length=10,
                    ),
                ),
                ("title_override", models.CharField(blank=True, max_length=255)),
                ("short_description", models.CharField(blank=True, max_length=500)),
                ("explanation", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Control content",
                "verbose_name_plural": "Control content",
                "ordering": ["control_id", "soortvervoer"],
            },
        ),
        migrations.AddConstraint(
            model_name="controlcontent",
            constraint=models.UniqueConstraint(
                fields=("control_id", "soortvervoer"),
                name="uniq_control_content_control_soortvervoer",
            ),
        ),
    ]
