from rest_framework import serializers
from .models import Author


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['id', 'name', 'surname', 'patronymic', 'books']
        extra_kwargs = {
            'books': {'required': False}
        }
