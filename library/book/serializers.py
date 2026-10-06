from rest_framework import serializers
from .models import Book
from author.models import Author


class BookSerializer(serializers.ModelSerializer):
    available_count = serializers.IntegerField(read_only=True)
    authors = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Author.objects.all(),
        required=False
    )

    class Meta:
        model = Book
        fields = ['id', 'name', 'description', 'count', 'available_count', 'authors']
