from django.core.validators import MinValueValidator
from django.db import models, router, transaction
from django.db.models import Count, Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from pgvector.django import VectorField

from audit.services import record


class BookQuerySet(models.QuerySet):
    def bulk_create(self, *args, **kwargs):
        raise ValueError(
            "Book bulk_create bypasses embeddings; use create() or save()."
        )

    def update(self, **kwargs):
        if {"name", "description"}.intersection(kwargs):
            raise ValueError("Book text update bypasses embeddings; use save().")
        if "count" in kwargs:
            raise ValueError("Book stock update bypasses the audit trail; use save().")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        fields = tuple(fields)
        if {"name", "description"}.intersection(fields):
            raise ValueError("Book text bulk_update bypasses embeddings; use save().")
        if "count" in fields:
            raise ValueError("Book stock update bypasses the audit trail; use save().")
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def with_availability(self):
        """Count unreturned orders in SQL, including books with no orders.

        Distinct order IDs prevent author joins from multiplying the count.
        Annotations are a snapshot; refetch after changing orders.
        """
        return self.annotate(
            active_order_count=Count(
                "order", filter=Q(order__end_at__isnull=True), distinct=True
            )
        )


class Book(models.Model):
    """
    This class represents an Author. \n
    Attributes:
    -----------
    param name: Describes name of the book
    type name: str max_length=128
    param description: Describes description of the book
    type description: str
    param count: Describes count of the book
    type count: int default=10
    param authors: list of Authors
    type authors: list->Author
    """

    NAME_MAX_LEN = 128
    DESCRIPTION_MAX_LEN = 256
    DEFAULT_COUNT = 10
    # Loans and reservations protect a book (FR-024); every channel says so.
    DELETION_REFUSAL = (
        "This book cannot be deleted because it has borrowing or reservation history."
    )

    name = models.CharField(blank=True, max_length=NAME_MAX_LEN)
    description = models.CharField(blank=True, max_length=DESCRIPTION_MAX_LEN)
    count = models.IntegerField(
        default=DEFAULT_COUNT, validators=[MinValueValidator(0)]
    )
    id = models.AutoField(primary_key=True)
    objects = BookQuerySet.as_manager()

    def __str__(self):
        return self.name

    def __repr__(self):
        """
        This magic method is redefined to show class and id of Book object.
        :return: class, id
        """
        return f"Book(id={self.id})"

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        """Keep book text and its embedding consistent in a single transaction.

        Normal ORM saves, web forms, API and admin all use this path.
        Bulk creation and bulk text writes are rejected by the queryset.
        """
        from .embedding_config import resolve
        from .embeddings import (
            document_text,
            input_hash,
            regenerate_book_embedding,
        )

        if update_fields is not None:
            update_fields = frozenset(update_fields)
            if not update_fields:
                return
        database = using or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=database):
            previous = None
            if self.pk is not None:
                previous = (
                    type(self)
                    .objects.using(database)
                    .select_for_update()
                    .filter(pk=self.pk)
                    .values("count")
                    .first()
                )
            result = super().save(
                force_insert=force_insert,
                force_update=force_update,
                using=database,
                update_fields=update_fields,
            )
            # Read what actually persisted, including partial update_fields.
            current = type(self).objects.using(database).get(pk=self.pk)
            existing = (
                BookEmbedding.objects.using(database)
                .filter(book_id=self.pk)
                .values(
                    "input_hash",
                    "model",
                    "model_revision",
                )
                .first()
            )
            if existing is None or (
                existing["input_hash"]
                != input_hash(document_text(current.name, current.description))
                or existing["model"] != resolve().repository
                or existing["model_revision"] != resolve().tag
            ):
                regenerate_book_embedding(current, database)
                self._state.fields_cache.pop("embedding", None)
            # A change of total copies is audited with it (FR-037, FR-040).
            if previous is not None and current.count != previous["count"]:
                before, after = {"count": previous["count"]}, {"count": current.count}
                record(
                    "book_copies_changed", "book", self.pk, current.name, before, after
                )
            return result

    @property
    def available_count(self):
        """Derived availability, without a separately persisted stock counter."""
        active_orders = getattr(self, "active_order_count", None)
        if active_orders is None:
            active_orders = 0
            if self.pk is not None:
                active_orders = self.order_set.aggregate(
                    active_count=Count("pk", filter=Q(end_at__isnull=True))
                )["active_count"]
        return max(0, self.count - active_orders)

    @staticmethod
    def get_by_id(book_id):
        """
        :param book_id: SERIAL: the id of a Book to be found in the DB
        :return: book object or None if a book with such ID does not exist
        """
        return Book.objects.get(id=book_id) if Book.objects.filter(id=book_id) else None

    @staticmethod
    def delete_by_id(book_id):
        """
        :param book_id: an id of a book to be deleted
        :type book_id: int
        :return: True if object existed in the db and was removed or False if it didn't exist
        """
        if Book.get_by_id(book_id) is None:
            return False
        Book.objects.get(id=book_id).delete()
        return True

    @staticmethod
    def create(name, description, count=DEFAULT_COUNT, authors=None):
        """
        param name: Describes name of the book
        type name: str max_length=128
        param description: Describes description of the book
        type description: str
        param count: Describes count of the book
        type count: int default=10
        param authors: list of Authors
        type authors: list->Author
        :return: a new book object which is also written into the DB
        """
        if len(name) > Book.NAME_MAX_LEN:
            return None

        book = Book()
        book.name = name
        book.description = description
        book.count = count
        if authors is not None:
            for elem in authors:
                book.authors.add(elem)
        book.save()
        return book

    def to_dict(self):
        """
        :return: book id, book name, book description, book count, book authors
        :Example:
        | {
        |   'id': 8,
        |   'name': 'django book',
        |   'description': 'bla bla bla',
        |   'count': 10',
        |   'authors': []
        | }
        """

    def update(self, name=None, description=None, count=None):
        """
        Updates book in the database with the specified parameters.\n
        param name: Describes name of the book
        type name: str max_length=128
        param description: Describes description of the book
        type description: str
        param count: Describes count of the book
        type count: int default=10
        :return: None
        """
        if name is not None:
            self.name = name

        if description is not None:
            self.description = description

        if count is not None:
            self.count = count

        self.save()

    def add_authors(self, authors):
        """
        Add  authors to  book in the database with the specified parameters.\n
        param authors: list authors
        :return: None
        """
        if authors is not None:
            for elem in authors:
                self.authors.add(elem)
                self.save()

    def remove_authors(self, authors):
        """
        Remove authors to  book in the database with the specified parameters.\n
        param authors: list authors
        :return: None
        """
        for elem in self.authors.values():
            self.authors.remove(elem["id"])

    @staticmethod
    def get_all():
        """
        returns data for json request with QuerySet of all books
        """
        return list(Book.objects.all())


@receiver(post_delete, sender=Book, dispatch_uid="book.book_deleted")
def record_book_deletion(sender, instance, **kwargs):
    before = {"name": instance.name, "count": instance.count}
    record("book_deleted", "book", instance.pk, instance.name, before, {})


class BookEmbedding(models.Model):  # noqa: DJ008
    """A reproducible document embedding, kept separate from catalog responses."""

    book = models.OneToOneField(
        Book,
        on_delete=models.CASCADE,
        related_name="embedding",
        primary_key=True,
    )
    # Untyped, so the vector size can follow the configured model.
    vector = VectorField()
    input_hash = models.CharField(max_length=64)
    model = models.CharField(max_length=100)
    model_revision = models.CharField(max_length=40)
    updated_at = models.DateTimeField(auto_now=True)
