from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import Group

from .models import CustomUser
from .services import (
    ASSIGNABLE_ROLE_CHOICES,
    may_change_account,
    may_change_role,
    update_account,
)

admin.site.unregister(Group)


class CustomUserChangeForm(UserChangeForm):
    """The password hash is read-only, with a link to the change-password form."""

    class Meta:
        model = CustomUser
        fields = (
            "email",
            "password",
            "first_name",
            "middle_name",
            "last_name",
            "role",
            "is_active",
        )


class CustomUserCreationForm(AdminUserCreationForm):
    class Meta:
        model = CustomUser
        fields = ("email", "first_name", "middle_name", "last_name", "is_active")


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Accounts in the admin site, under the same rule as the web and the API: the
    role only for administrators, and an administrator's account read-only for
    librarians (FR-063). The password is set only on the add form and the
    change-password form, never by editing the hash (TD-23)."""

    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "middle_name",
                    "last_name",
                    "is_active",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    ordering = ("email",)
    filter_horizontal = ()

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
        if not change:
            # The add form has already hashed the new password.
            super().save_model(request, obj, form, change)
            return
        # The changed fields go through the rule; the read-only hash never changes.
        changes = {name: form.cleaned_data[name] for name in form.changed_data}
        update_account(request.user, obj, changes)
