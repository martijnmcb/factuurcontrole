import json

from django.core.management.base import BaseCommand, CommandError

from apps.clients.models import Client
from apps.sync_jobs.models import SyncRun


class Command(BaseCommand):
    help = "Show metadata for the most recent sync run of a client."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--client", required=True, help="Client slug")

    def handle(self, *args, **options) -> None:
        slug = options["client"]
        try:
            client = Client.objects.get(slug=slug)
        except Client.DoesNotExist as exc:
            raise CommandError(f"Unknown client: {slug}") from exc

        sync_run = SyncRun.objects.filter(client=client).order_by("-started_at").first()
        if not sync_run:
            raise CommandError(f"No sync runs found for client: {slug}")

        self.stdout.write(json.dumps(sync_run.metadata, indent=2, default=str))
