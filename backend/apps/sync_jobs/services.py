from __future__ import annotations

import logging
import threading

from django.db import close_old_connections
from django.utils import timezone

from apps.clients.models import Client
from sync_pipeline.jobs.sync_client import run_client_sync

from .models import SyncRun, SyncRunStatus

logger = logging.getLogger(__name__)
_running_sync_ids: set[int] = set()


class SyncOrchestrator:
    def _mark_stale_sync_failed(self, sync_run: SyncRun) -> SyncRun:
        sync_run.status = SyncRunStatus.FAILED
        sync_run.finished_at = timezone.now()
        sync_run.message = "Refresh interrupted by application restart or worker shutdown"
        sync_run.metadata = {
            **(sync_run.metadata or {}),
            "progress": {
                "stage": "failed",
                "message": sync_run.message,
                "percent": None,
            },
        }
        sync_run.save(update_fields=["status", "finished_at", "message", "metadata", "updated_at"])
        return sync_run

    def _reconcile_sync_run(self, sync_run: SyncRun | None) -> SyncRun | None:
        if sync_run is None:
            return None
        if sync_run.status == SyncRunStatus.STARTED and sync_run.id not in _running_sync_ids:
            return self._mark_stale_sync_failed(sync_run)
        return sync_run

    def _run_sync(self, sync_run: SyncRun, client: Client) -> SyncRun:
        sync_run = SyncRun.objects.create(client=client, started_at=timezone.now())
        return self._execute_sync(sync_run, client)

    def _execute_sync(self, sync_run: SyncRun, client: Client) -> SyncRun:
        def update_progress(stage: str, message: str, percent: int | None = None) -> None:
            metadata = dict(sync_run.metadata or {})
            metadata["progress"] = {
                "stage": stage,
                "message": message,
                "percent": percent,
            }
            sync_run.metadata = metadata
            sync_run.message = message
            sync_run.save(update_fields=["metadata", "message", "updated_at"])

        try:
            update_progress("starting", "Starting refresh", 0)
            result = run_client_sync(client, progress_callback=update_progress)
            sync_run.status = SyncRunStatus.SUCCESS
            sync_run.records_synced = result.records_synced
            sync_run.metadata = result.metadata
            sync_run.message = result.message
            logger.info("Client sync succeeded", extra={"client": client.slug, "records": result.records_synced})
        except Exception as exc:  # noqa: BLE001
            sync_run.status = SyncRunStatus.FAILED
            sync_run.metadata = {
                **(sync_run.metadata or {}),
                "progress": {
                    "stage": "failed",
                    "message": str(exc),
                    "percent": None,
                },
            }
            sync_run.message = str(exc)
            logger.exception("Client sync failed", extra={"client": client.slug})
            raise
        finally:
            sync_run.finished_at = timezone.now()
            sync_run.save(update_fields=["status", "finished_at", "records_synced", "message", "metadata", "updated_at"])
        return sync_run

    def sync_client(self, client: Client) -> SyncRun:
        sync_run = SyncRun.objects.create(client=client, started_at=timezone.now())
        return self._execute_sync(sync_run, client)

    def get_running_sync(self, client: Client) -> SyncRun | None:
        running = client.sync_runs.filter(status=SyncRunStatus.STARTED).first()
        running = self._reconcile_sync_run(running)
        if running and running.status == SyncRunStatus.STARTED:
            return running
        return None

    def get_latest_sync(self, client: Client) -> SyncRun | None:
        latest = client.sync_runs.first()
        return self._reconcile_sync_run(latest)

    def sync_client_async(self, client: Client) -> tuple[SyncRun, bool]:
        running = self.get_running_sync(client)
        if running:
            return running, False

        sync_run = SyncRun.objects.create(client=client, started_at=timezone.now())
        _running_sync_ids.add(sync_run.id)

        def target() -> None:
            close_old_connections()
            try:
                self._execute_sync(sync_run, client)
            except Exception:  # noqa: BLE001
                pass
            finally:
                _running_sync_ids.discard(sync_run.id)
                close_old_connections()

        thread = threading.Thread(target=target, name=f"sync-client-{client.slug}", daemon=True)
        thread.start()
        return sync_run, True
