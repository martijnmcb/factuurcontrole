from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Client",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="DataSourceConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("server", models.CharField(max_length=255)),
                ("database", models.CharField(max_length=255)),
                ("username", models.CharField(blank=True, max_length=255)),
                ("password", models.CharField(blank=True, max_length=255)),
                ("driver", models.CharField(default="ODBC Driver 18 for SQL Server", max_length=255)),
                ("extra_params", models.JSONField(blank=True, default=dict)),
                ("is_enabled", models.BooleanField(default=True)),
                ("client", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="data_source_config", to="clients.client")),
            ],
        ),
        migrations.CreateModel(
            name="SyncConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("parquet_root", models.CharField(blank=True, max_length=500)),
                ("full_refresh", models.BooleanField(default=False)),
                ("enabled", models.BooleanField(default=True)),
                ("schedule", models.CharField(blank=True, max_length=100)),
                ("client", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sync_config", to="clients.client")),
            ],
        ),
        migrations.CreateModel(
            name="ClientAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_access", to="clients.client")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="client_access", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Client access", "verbose_name_plural": "Client access", "unique_together": {("user", "client")}},
        ),
    ]
