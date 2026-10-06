from django.contrib import admin, messages
from django.shortcuts import redirect
from .models import Book
from .embeddings import EmbeddingGenerationError
from order.models import Order


class OrderInline(admin.TabularInline):
    """Секція динамічних даних про видачу книги"""
    model = Order
    extra = 0
    fields = ('user', 'created_at', 'plated_end_at', 'end_at')
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except EmbeddingGenerationError as error:
            self.message_user(request, str(error), level=messages.ERROR)
            return redirect(request.path)

    list_display = ('id', 'name', 'count', 'get_authors', 'description')
    list_filter = ('id', 'name', 'authors')
    search_fields = ('id', 'name', 'authors__name', 'authors__surname')

    fieldsets = (
        ('Static data', {
            'fields': ('name', 'description', 'get_authors'),
            'description': 'Main information about the book, which does not change.'
        }),
        ('Dynamic data', {
            'fields': ('count',),
            'description': 'Count of copies available.'
        }),
    )
    inlines = [OrderInline]

    def get_readonly_fields(self, request, obj=None):
        return ('get_authors',)

    @admin.display(description='Authors')
    def get_authors(self, obj):
        authors = obj.authors.all()
        return ", ".join([str(a) for a in authors]) if authors.exists() else "No authors"
