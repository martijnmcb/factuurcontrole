from django.contrib import admin

from .models import Client, ClientAccess, DataSourceConfig, SyncConfig


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)


@admin.register(DataSourceConfig)
class DataSourceConfigAdmin(admin.ModelAdmin):
    list_display = ("client", "server", "database", "driver", "is_enabled")
    search_fields = ("client__name", "server", "database")
    list_filter = ("is_enabled",)


@admin.register(SyncConfig)
class SyncConfigAdmin(admin.ModelAdmin):
    list_display = ("client", "enabled", "full_refresh", "schedule")
    list_filter = ("enabled", "full_refresh")


@admin.register(ClientAccess)
class ClientAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "client", "updated_at")
    search_fields = ("user__username", "client__name")
