from django.db import models, DataError, router, transaction

from authentication.models import CustomUser
from book.models import Book


class BookUnavailableError(ValueError):
    """An active order cannot consume a copy that is already on loan."""


class Order(models.Model):
    """
           This class represents an Order. \n
           Attributes:
           -----------
           param book: foreign key Book
           type book: ForeignKey
           param user: foreign key CustomUser
           type user: ForeignKey
           param created_at: Describes the date when the order was created. Can't be changed.
           type created_at: int (timestamp)
           param end_at: Describes the actual return date of the book. (`None` if not returned)
           type end_at: int (timestamp)
           param plated_end_at: Describes the planned return period of the book (2 weeks from the moment of creation).
           type plated_end_at: int (timestamp)
       """
    book = models.ForeignKey(Book, on_delete=models.CASCADE, default=None)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    end_at = models.DateTimeField(default=None, null=True, blank=True)
    plated_end_at = models.DateTimeField(default=None)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """Serialize issuance, reopening and book reassignment on the Book row.

        Availability is derived from active orders; creating an order consumes
        a copy without changing Book.count or a separate stock counter.
        Use save/create for these operations, not bulk_create/QuerySet.update.
        """
        if update_fields is not None:
            update_fields = frozenset(update_fields)
            if not update_fields:
                return
        database = using or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=database):
            previous = None
            if self.pk is not None:
                previous = type(self).objects.using(database).select_for_update().filter(
                    pk=self.pk
                ).values('book_id', 'end_at').first()
            book_id, end_at = self.book_id, self.end_at
            if previous is not None and update_fields is not None:
                if not {'book', 'book_id'} & update_fields:
                    book_id = previous['book_id']
                if 'end_at' not in update_fields:
                    end_at = previous['end_at']
            consumes_copy = end_at is None and (
                previous is None or previous['end_at'] is not None
                or previous['book_id'] != book_id
            )
            if consumes_copy:
                # Keep the locking query free of joins/aggregations. Recount
                # after acquiring the lock, using a fresh, unannotated Book.
                book = Book.objects.using(database).select_for_update().get(pk=book_id)
                if book.available_count <= 0:
                    raise BookUnavailableError('No copies of this book are currently available.')
            return super().save(
                force_insert=force_insert, force_update=force_update,
                using=database, update_fields=update_fields,
            )

    def __str__(self):
        return f"Order #{self.id} ({self.user.email} - {self.book.name})"

    def __repr__(self):
        """
        This magic method is redefined to show class and id of Book object.
        :return: class, id
        """
        return f'{self.__class__.__name__}(id={self.id})'

    def to_dict(self):
        """
                :return: order id, book id, user id, order created_at, order end_at, order plated_end_at
                :Example:
                | {
                |   'id': 8,
                |   'book': 8,
                |   'user': 8',
                |   'created_at': 1509393504,
                |   'end_at': 1509393504,
                |   'plated_end_at': 1509402866,
                | }
                """
        pass

    @staticmethod
    def create(user, book, plated_end_at):
        try:
            order = Order(user=user, book=book, plated_end_at=plated_end_at)
            order.save()
            return order
        except ValueError:
            return None
        except DataError:
            return None

    @staticmethod
    def get_by_id(order_id):
        try:
            return Order.objects.get(pk=order_id)
        except:
            return None

    def update(self, plated_end_at=None, end_at=None):
        if plated_end_at != None:
            self.plated_end_at = plated_end_at
        if end_at != None:
            self.end_at = end_at
        self.save()

    @staticmethod
    def get_all():
        return list(Order.objects.all())

    @staticmethod
    def get_not_returned_books():
        return Order.objects.filter(end_at=None).values()

    @staticmethod
    def delete_by_id(order_id):
        try:
            a = Order.objects.get(pk=order_id)
        except:
            return False
        else:
            a.delete()
            return True
