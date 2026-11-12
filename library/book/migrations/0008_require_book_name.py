from django.db import migrations, models
from django.db.models import Q


def name_untitled_books(apps, schema_editor):
    """Books saved without a title before KAN-81 get one, so the constraint holds.
    Loans and reservations may refer to them, so they are not deleted."""
    Book = apps.get_model("book", "Book")
    for pk in Book.objects.exclude(name__regex=r"\S").values_list("pk", flat=True):
        Book.objects.filter(pk=pk).update(name=f"Untitled book #{pk}")


class Migration(migrations.Migration):

    dependencies = [
        ("book", "0007_book_rating"),
    ]

    operations = [
        migrations.RunPython(name_untitled_books, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="book",
            name="name",
            field=models.CharField(max_length=128),
        ),
        migrations.AddConstraint(
            model_name="book",
            constraint=models.CheckConstraint(
                condition=Q(name__regex=r"\S"), name="book_name_not_blank"
            ),
        ),
    ]
