from django.contrib import admin

from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    """Where librarians read the trail. Nobody adds, changes or deletes an entry."""

    list_display = ("occurred_at", "action", "actor_label", "target_label", "channel")
    list_filter = ("action", "channel", "occurred_at")
    search_fields = ("actor_label", "target_label")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
