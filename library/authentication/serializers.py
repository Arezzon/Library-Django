from rest_framework import serializers

from .models import CustomUser
from .services import ASSIGNABLE_ROLES, update_account


class CustomUserSerializer(serializers.ModelSerializer):
    """An account. Only an administrator may set the role, as reader or librarian, and
    only a librarian the status, email or password."""

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "password",
            "created_at",
            "updated_at",
            "role",
            "is_active",
        ]
        extra_kwargs = {
            "password": {"write_only": True, "required": False},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
            "role": {
                "help_text": (
                    "0 reader, 1 librarian, 2 administrator. Only an administrator "
                    "sets it, to reader or librarian; the operator grants the "
                    "administrator role on the server."
                )
            },
        }

    def get_fields(self):
        fields = super().get_fields()
        if not self.requested_by("is_administrator"):
            fields["role"].read_only = True
        if not self.requested_by("is_librarian"):
            for name in ("is_active", "email"):
                fields[name].read_only = True
            del fields["password"]
        return fields

    def requested_by(self, right):
        """Whether the caller has ``right``, a role property such as is_librarian."""
        # The schema documents every field an administrator may write.
        if getattr(self.context.get("view"), "swagger_fake_view", False):
            return True
        request = self.context.get("request")
        return bool(request and getattr(request.user, right, False))

    def validate_role(self, role):
        # Every role is listed, since responses carry all three; two are assignable.
        if role not in ASSIGNABLE_ROLES:
            raise serializers.ValidationError(
                "The operator grants the administrator role on the server."
            )
        return role

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = CustomUser(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        return update_account(self.context["request"].user, instance, validated_data)
