from django.contrib import admin, messages
from django.shortcuts import redirect
from .models import Order, BookUnavailableError


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except BookUnavailableError as error:
            # The admin's enclosing transaction rolls back before this handler.
            self.message_user(request, str(error), level=messages.ERROR)
            return redirect(request.path)

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
