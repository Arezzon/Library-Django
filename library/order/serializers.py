from rest_framework import serializers
from .models import Order


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['id', 'user', 'book', 'created_at', 'end_at', 'plated_end_at']
        extra_kwargs = {
            'created_at': {'read_only': True},
            'end_at': {'required': False, 'allow_null': True},
        }
