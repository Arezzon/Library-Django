from django.contrib import admin
from .models import Book
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
        if obj:
            return ('name', 'description', 'get_authors')
        return ('get_authors',)

    @admin.display(description='Authors')
    def get_authors(self, obj):
        authors = obj.authors.all()
        return ", ".join([str(a) for a in authors]) if authors.exists() else "No authors"
