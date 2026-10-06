from rest_framework import serializers
from .models import Book
from author.models import Author
from .embeddings import EmbeddingGenerationError


class BookSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except EmbeddingGenerationError as error:
            raise serializers.ValidationError({'description': str(error)}) from error

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except EmbeddingGenerationError as error:
            raise serializers.ValidationError({'description': str(error)}) from error

    available_count = serializers.IntegerField(read_only=True)
    authors = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Author.objects.all(),
        required=False
    )

    class Meta:
        model = Book
        fields = ['id', 'name', 'description', 'count', 'available_count', 'authors']
