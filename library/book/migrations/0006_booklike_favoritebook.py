from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("book", "0005_alter_book_count"),
    ]
    operations = [
        migrations.CreateModel(
            name="BookLike",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("book", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="likes", to="book.book")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="book_likes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at", "-book_id"],
                "indexes": [models.Index(fields=["user", "-created_at"], name="book_like_user_recent")],
                "constraints": [models.UniqueConstraint(fields=("user", "book"), name="one_like_per_reader_book")],
            },
        ),
        migrations.CreateModel(
            name="FavoriteBook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("book", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorite_entries", to="book.book")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="book_favorites", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at", "-book_id"],
                "indexes": [models.Index(fields=["user", "-created_at"], name="book_fav_user_recent")],
                "constraints": [models.UniqueConstraint(fields=("user", "book"), name="one_favorite_per_reader_book")],
            },
        ),
    ]
