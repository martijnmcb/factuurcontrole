from __future__ import annotations

import logging

from django.utils import timezone

from apps.clients.models import Client
from sync_pipeline.jobs.sync_client import run_client_sync

from .models import SyncRun, SyncRunStatus

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    def sync_client(self, client: Client) -> SyncRun:
        sync_run = SyncRun.objects.create(client=client, started_at=timezone.now())
        try:
            result = run_client_sync(client)
            sync_run.status = SyncRunStatus.SUCCESS
            sync_run.records_synced = result.records_synced
            sync_run.metadata = result.metadata
            sync_run.message = result.message
            logger.info("Client sync succeeded", extra={"client": client.slug, "records": result.records_synced})
        except Exception as exc:  # noqa: BLE001
            sync_run.status = SyncRunStatus.FAILED
            sync_run.message = str(exc)
            logger.exception("Client sync failed", extra={"client": client.slug})
            raise
        finally:
            sync_run.finished_at = timezone.now()
            sync_run.save(update_fields=["status", "finished_at", "records_synced", "message", "metadata", "updated_at"])
        return sync_run
