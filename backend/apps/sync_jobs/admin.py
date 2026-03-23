from django.contrib import admin

from .models import SyncRun


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = ("client", "status", "started_at", "finished_at", "records_synced")
    list_filter = ("status", "client")
    search_fields = ("client__name", "message")
