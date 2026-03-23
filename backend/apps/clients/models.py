from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Client(TimeStampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DataSourceConfig(TimeStampedModel):
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="data_source_config")
    server = models.CharField(max_length=255)
    database = models.CharField(max_length=255)
    username = models.CharField(max_length=255, blank=True)
    password = models.CharField(max_length=255, blank=True)
    driver = models.CharField(max_length=255, default="ODBC Driver 18 for SQL Server")
    extra_params = models.JSONField(default=dict, blank=True)
    is_enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.client.slug} datasource"


class SyncConfig(TimeStampedModel):
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="sync_config")
    parquet_root = models.CharField(max_length=500, blank=True)
    full_refresh = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    schedule = models.CharField(max_length=100, blank=True)

    def __str__(self) -> str:
        return f"{self.client.slug} sync config"


class ClientAccess(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="client_access")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="user_access")

    class Meta:
        unique_together = ("user", "client")
        verbose_name = "Client access"
        verbose_name_plural = "Client access"

    def __str__(self) -> str:
        return f"{self.user} -> {self.client.slug}"
