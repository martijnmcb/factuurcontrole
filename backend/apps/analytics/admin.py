from django.contrib import admin

from .models import ControlContent


@admin.register(ControlContent)
class ControlContentAdmin(admin.ModelAdmin):
    list_display = ("control_id", "soortvervoer", "title_override", "is_active", "updated_at")
    list_filter = ("soortvervoer", "is_active")
    search_fields = ("control_id", "title_override", "short_description", "explanation")
    ordering = ("control_id", "soortvervoer")
