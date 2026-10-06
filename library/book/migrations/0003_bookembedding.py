from django.db import migrations, models
import django.db.models.deletion
from pgvector.django import VectorExtension, VectorField


class Migration(migrations.Migration):
    dependencies = [('book', '0002_book_count_book_description_book_name_alter_book_id')]

    operations = [
        VectorExtension(),
        migrations.CreateModel(
            name='BookEmbedding',
            fields=[
                ('book', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE, primary_key=True,
                    related_name='embedding', serialize=False, to='book.book',
                )),
                ('vector', VectorField(dimensions=384)),
                ('input_hash', models.CharField(max_length=64)),
                ('model', models.CharField(max_length=100)),
                ('model_revision', models.CharField(max_length=40)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
