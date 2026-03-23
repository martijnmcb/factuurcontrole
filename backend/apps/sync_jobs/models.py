from django.db import models

from apps.clients.models import Client
from apps.core.models import TimeStampedModel


class SyncRunStatus(models.TextChoices):
    STARTED = "started", "Started"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class SyncRun(TimeStampedModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="sync_runs")
    status = models.CharField(max_length=20, choices=SyncRunStatus.choices, default=SyncRunStatus.STARTED)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    records_synced = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.client.slug} {self.started_at:%Y-%m-%d %H:%M:%S} {self.status}"
