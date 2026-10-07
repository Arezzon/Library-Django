import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='UserEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_type', models.CharField(max_length=32, choices=[
                    ('book_view', 'Book viewed'), ('search', 'Catalog searched'),
                    ('book_click', 'Book clicked'), ('borrow_intent', 'Borrow button clicked'),
                    ('order_created', 'Book borrowed'), ('order_returned', 'Book returned'),
                    ('order_reopened', 'Order reopened'), ('order_reassigned', 'Order reassigned'),
                    ('login', 'Signed in'), ('logout', 'Signed out'),
                ])),
                ('source', models.CharField(max_length=8, choices=[('server', 'Server'), ('client', 'Client')])),
                ('book_id', models.PositiveBigIntegerField(blank=True, null=True)),
                ('path', models.CharField(blank=True, max_length=200)),
                ('properties', models.JSONField(blank=True, default=dict)),
                ('occurred_at', models.DateTimeField()),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                          related_name='events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-occurred_at', '-id'],
                'indexes': [
                    models.Index(fields=['occurred_at'], name='event_occurred_idx'),
                    models.Index(fields=['user', 'event_type', 'occurred_at'], name='event_user_type_time_idx'),
                    models.Index(fields=['book_id', 'event_type'], name='event_book_type_idx'),
                ],
            },
        ),
    ]
