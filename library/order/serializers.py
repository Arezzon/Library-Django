from rest_framework import serializers
from .models import Order, BookUnavailableError


class OrderSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except BookUnavailableError as error:
            raise serializers.ValidationError({'book': str(error)}) from error

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except BookUnavailableError as error:
            raise serializers.ValidationError({'book': str(error)}) from error

    class Meta:
        model = Order
        fields = ['id', 'user', 'book', 'created_at', 'end_at', 'plated_end_at']
        extra_kwargs = {
            'created_at': {'read_only': True},
            'end_at': {'required': False, 'allow_null': True},
        }
