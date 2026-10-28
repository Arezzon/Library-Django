from rest_framework import serializers

from .models import CustomUser
from .services import update_account


class CustomUserSerializer(serializers.ModelSerializer):
    """An account. Only a librarian may set the role, status, email or password."""

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
        }

    def get_fields(self):
        fields = super().get_fields()
        if not self.requested_by_librarian():
            for name in ("role", "is_active", "email"):
                fields[name].read_only = True
            del fields["password"]
        return fields

    def requested_by_librarian(self):
        # The schema documents every field a librarian may write.
        if getattr(self.context.get("view"), "swagger_fake_view", False):
            return True
        request = self.context.get("request")
        return bool(request and getattr(request.user, "is_librarian", False))

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = CustomUser(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        return update_account(self.context["request"].user, instance, validated_data)
