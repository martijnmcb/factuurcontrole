from django.core.management.base import BaseCommand, CommandError

from apps.clients.models import Client
from apps.sync_jobs.services import SyncOrchestrator


class Command(BaseCommand):
    help = "Synchronize SQL Server data for a single client into Parquet datasets."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--client", required=True, help="Client slug")

    def handle(self, *args, **options) -> None:
        slug = options["client"]
        try:
            client = Client.objects.get(slug=slug, is_active=True)
        except Client.DoesNotExist as exc:
            raise CommandError(f"Unknown active client: {slug}") from exc

        sync_run = SyncOrchestrator().sync_client(client)
        self.stdout.write(
            self.style.SUCCESS(
                f"Sync finished for {client.slug} with status={sync_run.status} records={sync_run.records_synced}"
            )
        )
