from django.contrib import admin
from django.contrib.auth.models import Group

from .models import CustomUser
from .services import (
    ASSIGNABLE_ROLE_CHOICES,
    may_change_account,
    may_change_role,
    update_account,
)

admin.site.unregister(Group)


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    """Accounts in the admin site, under the same rule as the web and the API: the
    role only for administrators, and an administrator's account read-only for
    librarians (FR-063)."""

    list_display = (
        "id",
        "email",
        "first_name",
        "last_name",
        "role",
        "is_active",
        "created_at",
    )

    list_filter = ("role", "is_active", "created_at")

    search_fields = ("email", "first_name", "last_name")

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Account data", {"fields": ("email", "password")}),
        (
            "Personal information",
            {"fields": ("first_name", "middle_name", "last_name")},
        ),
        (
            "Rights and status",
            {"fields": ("role", "is_active", "created_at", "updated_at")},
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        if may_change_role(request.user, obj):
            return self.readonly_fields
        return (*self.readonly_fields, "role")

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "role":
            kwargs["choices"] = ASSIGNABLE_ROLE_CHOICES
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and may_change_account(
            request.user, obj
        )

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and may_change_account(
            request.user, obj
        )

    def save_model(self, request, obj, form, change):
        # The changed fields go through the rule; a changed password is hashed.
        changes = {name: form.cleaned_data[name] for name in form.changed_data}
        update_account(request.user, obj, changes)
