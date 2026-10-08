from django.contrib import admin
from .models import UserEvent


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    list_display = ('occurred_at', 'event_type', 'user', 'source', 'book_id')
    list_filter = ('event_type', 'source', 'occurred_at')
    readonly_fields = ('id', 'user', 'event_type', 'source', 'book_id', 'path', 'properties', 'occurred_at', 'recorded_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
