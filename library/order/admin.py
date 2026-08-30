from django.contrib import admin
from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'book', 'created_at', 'plated_end_at', 'end_at')
    list_filter = ('book__id', 'book__name', 'book__authors', 'created_at', 'end_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'book__name', 'book__id')
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Order details', {
            'fields': ('user', 'book')
        }),
        ('Issue and return dates', {
            'fields': ('created_at', 'plated_end_at', 'end_at')
        }),
    )
