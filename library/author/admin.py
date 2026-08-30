from django.contrib import admin
from .models import Author


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('id', 'surname', 'name', 'patronymic', 'get_books_count')
    
    list_filter = ('surname', 'name')
    search_fields = ('id', 'name', 'surname', 'patronymic')
    
    autocomplete_fields = ('books',)
    
    fieldsets = (
        ('Author information', {
            'fields': (('name', 'surname', 'patronymic'),)
        }),
        ('Books by author', {
            'fields': ('books',),
            'description': 'Select books written by this author'
        }),
    )

    def get_books_count(self, obj):
        return obj.books.count()
    get_books_count.short_description = 'Count of books'
