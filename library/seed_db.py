import os
import sys
import django
import datetime
from django.utils import timezone

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'library.settings')
django.setup()

from authentication.models import CustomUser, ROLE_VISITOR, ROLE_LIBRARIAN
from author.models import Author
from book.models import Book
from order.models import Order

DEFAULT_BORROW_DAYS = 14
SHORT_BORROW_DAYS = 10
CLOSED_ORDER_PLATED_DAYS_AGO = 5
CLOSED_ORDER_END_DAYS_AGO = 2


def _seed_users() -> dict[str, CustomUser]:
    """Create initial users and return dictionary of created user models."""
    users_data = [
        {
            "email": "librarian@library.com",
            "password": "admin123password",
            "first_name": "Anna",
            "middle_name": "Ivanivna",
            "last_name": "Kovalenko",
            "role": ROLE_LIBRARIAN,
        },
        {
            "email": "reader@library.com",
            "password": "reader123password",
            "first_name": "Oleh",
            "middle_name": "Petrovych",
            "last_name": "Melnyk",
            "role": ROLE_VISITOR,
        },
        {
            "email": "alice@library.com",
            "password": "alice123password",
            "first_name": "Alice",
            "middle_name": "Marie",
            "last_name": "Smith",
            "role": ROLE_VISITOR,
        },
        {
            "email": "bob@library.com",
            "password": "bob123password",
            "first_name": "Bob",
            "middle_name": "John",
            "last_name": "Williams",
            "role": ROLE_VISITOR,
        },
    ]

    created_users = {}
    for u_data in users_data:
        user = CustomUser.objects.filter(email=u_data["email"]).first()
        if not user:
            user = CustomUser.objects.create_user(
                email=u_data["email"],
                password=u_data["password"],
                first_name=u_data["first_name"],
                middle_name=u_data["middle_name"],
                last_name=u_data["last_name"],
                role=u_data["role"],
                is_active=True
            )
            print(f"  + Created user: {user.email} (Role: {user.get_role_name()})")
        else:
            print(f"  - User already exists: {user.email}")
        created_users[u_data["email"]] = user
    return created_users


def _seed_authors() -> dict[str, Author]:
    """Create initial authors and return dictionary mapping surname to Author instance."""
    authors_data = [
        {"name": "Taras", "surname": "Shevchenko", "patronymic": "Hryhorovych"},
        {"name": "Ivan", "surname": "Franko", "patronymic": "Yakovych"},
        {"name": "Lesya", "surname": "Ukrainka", "patronymic": "Petrivna"},
        {"name": "George", "surname": "Orwell", "patronymic": "Arthur"},
        {"name": "Arthur", "surname": "Conan Doyle", "patronymic": "Ignatius"},
        {"name": "Robert", "surname": "Martin", "patronymic": "Cecil"},
        {"name": "J.K.", "surname": "Rowling", "patronymic": "Joanne"},
        {"name": "Mykola", "surname": "Gogol", "patronymic": "Vasyliovych"},
    ]

    created_authors = {}
    for a_data in authors_data:
        author, created = Author.objects.get_or_create(
            name=a_data["name"],
            surname=a_data["surname"],
            patronymic=a_data["patronymic"]
        )
        if created:
            print(f"  + Created author: {author.name} {author.surname}")
        else:
            print(f"  - Author already exists: {author.name} {author.surname}")
        created_authors[a_data["surname"]] = author
    return created_authors


def _seed_books(created_authors: dict[str, Author]) -> dict[str, Book]:
    """Create sample book catalog and attach author relations."""
    books_data = [
        {
            "name": "Kobzar",
            "description": "The seminal collection of poems by Taras Shevchenko, capturing the spirit and soul of Ukrainian literature.",
            "count": 5,
            "authors": ["Shevchenko"],
        },
        {
            "name": "Forest Song (Lisova Pisnya)",
            "description": "A poetic drama in three acts by Lesya Ukrainka exploring folklore and nature spirits.",
            "count": 4,
            "authors": ["Ukrainka"],
        },
        {
            "name": "Zakhar Berkut",
            "description": "Historical novella depicting the struggle of a 13th-century Carpathian community against the Mongol invaders.",
            "count": 6,
            "authors": ["Franko"],
        },
        {
            "name": "1984",
            "description": "A dystopian social science fiction novel and cautionary tale about totalitarianism and mass surveillance.",
            "count": 8,
            "authors": ["Orwell"],
        },
        {
            "name": "Animal Farm",
            "description": "A satirical allegorical novella reflecting events leading up to the Russian Revolution of 1917.",
            "count": 7,
            "authors": ["Orwell"],
        },
        {
            "name": "The Adventures of Sherlock Holmes",
            "description": "Classic detective short stories featuring the iconic detective Sherlock Holmes and Dr. Watson.",
            "count": 5,
            "authors": ["Conan Doyle"],
        },
        {
            "name": "Clean Code: A Handbook of Agile Software Craftsmanship",
            "description": "Best practices, patterns, and principles for writing maintainable and clean software code.",
            "count": 3,
            "authors": ["Martin"],
        },
        {
            "name": "Harry Potter and the Philosopher's Stone",
            "description": "The first novel in the Harry Potter series introducing Hogwarts School of Witchcraft and Wizardry.",
            "count": 10,
            "authors": ["Rowling"],
        },
        {
            "name": "Evenings on a Farm Near Dikanka",
            "description": "A vibrant collection of short stories blending Ukrainian folklore, humor, and supernatural elements.",
            "count": 4,
            "authors": ["Gogol"],
        },
    ]

    created_books = {}
    for b_data in books_data:
        book, created = Book.objects.get_or_create(
            name=b_data["name"],
            defaults={
                "description": b_data["description"],
                "count": b_data["count"]
            }
        )
        for a_surname in b_data["authors"]:
            if a_surname in created_authors:
                book.authors.add(created_authors[a_surname])

        if created:
            print(f"  + Created book: '{book.name}' (Stock: {book.count})")
        else:
            print(f"  - Book already exists: '{book.name}'")
        created_books[b_data["name"]] = book
    return created_books


def _seed_orders(created_users: dict[str, CustomUser], created_books: dict[str, Book]) -> None:
    """Create sample active and returned orders."""
    now = timezone.now()
    reader_user = created_users.get("reader@library.com")
    alice_user = created_users.get("alice@library.com")
    bob_user = created_users.get("bob@library.com")

    if reader_user and "Kobzar" in created_books:
        if not Order.objects.filter(user=reader_user, book=created_books["Kobzar"]).exists():
            Order.objects.create(
                user=reader_user,
                book=created_books["Kobzar"],
                plated_end_at=now + datetime.timedelta(days=DEFAULT_BORROW_DAYS),
                end_at=None
            )
            print("  + Created active order for reader@library.com: 'Kobzar'")

    if alice_user and "1984" in created_books:
        if not Order.objects.filter(user=alice_user, book=created_books["1984"]).exists():
            Order.objects.create(
                user=alice_user,
                book=created_books["1984"],
                plated_end_at=now + datetime.timedelta(days=SHORT_BORROW_DAYS),
                end_at=None
            )
            print("  + Created active order for alice@library.com: '1984'")

    if bob_user and "Clean Code: A Handbook of Agile Software Craftsmanship" in created_books:
        if not Order.objects.filter(user=bob_user, book=created_books["Clean Code: A Handbook of Agile Software Craftsmanship"]).exists():
            Order.objects.create(
                user=bob_user,
                book=created_books["Clean Code: A Handbook of Agile Software Craftsmanship"],
                plated_end_at=now - datetime.timedelta(days=CLOSED_ORDER_PLATED_DAYS_AGO),
                end_at=now - datetime.timedelta(days=CLOSED_ORDER_END_DAYS_AGO)
            )
            print("  + Created closed order for bob@library.com: 'Clean Code'")


def seed_data():
    print("[*] Starting database seeding...")
    created_users = _seed_users()
    created_authors = _seed_authors()
    created_books = _seed_books(created_authors)
    _seed_orders(created_users, created_books)
    print("\nDatabase successfully populated with sample data!")


if __name__ == "__main__":
    seed_data()
