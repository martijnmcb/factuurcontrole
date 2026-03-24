from django.db import migrations, models

import apps.clients.models


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datasourceconfig",
            name="extra_params",
            field=models.JSONField(blank=True, default=apps.clients.models.default_data_source_extra_params),
        ),
    ]
