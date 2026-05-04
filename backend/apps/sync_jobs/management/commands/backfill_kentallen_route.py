from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from django.core.management.base import BaseCommand, CommandError

from apps.clients.models import Client
from sync_pipeline.jobs.sync_client import _prepare_kentallen_route
from sync_pipeline.parquet.datasets import read_current_dataset, write_current_dataset
from sync_pipeline.sqlserver.connection import create_connection
from sync_pipeline.sqlserver.extractor import _discover_table_mapping, extract_kentallen_route


class Command(BaseCommand):
    help = "Backfill the kentallen_route dataset for current manifest runs."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--client", help="Optional client slug. Defaults to all active clients with a datasource.")

    def _get_manifest_run_ids(self, client: Client) -> list[int]:
        manifest = read_current_dataset(client.slug, "manifest")
        if manifest.empty or "stuurtabel_id" not in manifest.columns:
            return []

        run_ids = pd.to_numeric(manifest["stuurtabel_id"], errors="coerce").dropna()
        return sorted({int(value) for value in run_ids.tolist()})

    def _process_client(self, client: Client) -> tuple[int, int]:
        run_ids = self._get_manifest_run_ids(client)
        if not run_ids:
            self.stdout.write(self.style.WARNING(f"{client.slug}: no current manifest runs found, skipping"))
            return 0, 0

        with create_connection(client.data_source_config) as connection:
            discovered_tables = _discover_table_mapping(connection)
            raw = extract_kentallen_route(connection, run_ids, client.data_source_config, discovered_tables)

        prepared = _prepare_kentallen_route(raw, client.slug, run_ids, datetime.now(UTC))
        rows_written = write_current_dataset(prepared, client.slug, "kentallen_route")
        return len(run_ids), rows_written

    def handle(self, *args, **options) -> None:
        slug = options.get("client")
        if slug:
            clients = Client.objects.filter(slug=slug, is_active=True).select_related("data_source_config")
            if not clients.exists():
                raise CommandError(f"Unknown active client: {slug}")
        else:
            clients = Client.objects.filter(is_active=True, data_source_config__isnull=False).select_related("data_source_config")

        failures: list[str] = []
        for client in clients:
            try:
                run_count, row_count = self._process_client(client)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{client.slug}: backfilled kentallen_route for {run_count} runs ({row_count} rows written)"
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{client.slug}: {exc}")
                self.stdout.write(self.style.ERROR(f"{client.slug}: failed to backfill kentallen_route: {exc}"))

        if failures:
            raise CommandError("kentallen_route backfill completed with failures: " + " | ".join(failures))
