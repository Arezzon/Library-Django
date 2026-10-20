from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from authentication.decorators import librarian_required
from authentication.models import CustomUser
from author.models import Author
from order.models import Order

from .embeddings import EmbeddingGenerationError
from .forms import BookForm
from .models import Book
from .search import search_books


def _filter_books(query: str, author_id: str):
    """Filter book queryset by search query and/or author ID."""
    books = Book.objects.with_availability().prefetch_related("authors")

    if author_id and author_id.isdigit():
        books = books.filter(authors__id=int(author_id))

    books = books.distinct()
    return search_books(books, query) if query else books.order_by("id")


@login_required(login_url="login")
def book_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    author_id = request.GET.get("author_id", "").strip()

    try:
        books = _filter_books(query, author_id)
    except (ValueError, EmbeddingGenerationError) as error:
        messages.error(request, str(error))
        books = Book.objects.none()
    authors = Author.objects.all().order_by("surname", "name")

    return render(
        request,
        "book/book_list.html",
        {
            "books": books,
            "authors": authors,
            "query": query,
            "selected_author_id": int(author_id) if author_id.isdigit() else "",
        },
    )


@login_required(login_url="login")
def book_detail(request: HttpRequest, book_id: int) -> HttpResponse:
    book = get_object_or_404(
        Book.objects.with_availability().prefetch_related("authors"), pk=book_id
    )
    return render(request, "book/book_detail.html", {"book": book})


@librarian_required
def book_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = BookForm(request.POST)
        if form.is_valid():
            try:
                book = form.save()
            except EmbeddingGenerationError as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, f'Book "{book.name}" created successfully.')
                return redirect("book_list")
    else:
        form = BookForm()
    return render(request, "book/book_create.html", {"form": form})


@librarian_required
def book_update(request: HttpRequest, book_id: int) -> HttpResponse:
    book = get_object_or_404(Book, pk=book_id)
    if request.method == "POST":
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            try:
                form.save()
            except EmbeddingGenerationError as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, f'Book "{book.name}" updated successfully.')
                return redirect("book_detail", book_id=book.id)
    else:
        form = BookForm(instance=book)
    return render(request, "book/book_update.html", {"form": form, "book": book})


@librarian_required
@require_POST
def book_delete(request: HttpRequest, book_id: int) -> HttpResponse:
    with transaction.atomic():
        book = get_object_or_404(Book.objects.select_for_update(), pk=book_id)
        if Order.objects.filter(book_id=book_id).exists():
            messages.error(
                request, "This book cannot be deleted because it has borrowing history."
            )
            return redirect("book_update", book_id=book_id)

        name = book.name
        book.delete()

    messages.success(request, f'Book "{name}" deleted successfully.')
    return redirect("book_list")


@librarian_required
def books_by_user(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = get_object_or_404(CustomUser, pk=user_id)
    active_orders = Order.objects.filter(
        user=target_user, end_at__isnull=True
    ).select_related("book")

    return render(
        request,
        "book/books_by_user.html",
        {
            "target_user": target_user,
            "active_orders": active_orders,
        },
    )
