from django.contrib import admin
from .models import CustomUser

from django.contrib.auth.models import Group

admin.site.unregister(Group)


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'first_name', 'last_name', 'role', 'is_active', 'created_at')
    
    list_filter = ('role', 'is_active', 'created_at')
    
    search_fields = ('email', 'first_name', 'last_name')
    
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Account data', {
            'fields': ('email', 'password')
        }),
        ('Personal information', {
            'fields': ('first_name', 'middle_name', 'last_name')
        }),
        ('Rights and status', {
            'fields': ('role', 'is_active', 'created_at', 'updated_at')
        }),
    )
