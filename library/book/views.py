from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from authentication.decorators import librarian_required
from authentication.models import CustomUser
from .models import Book
from author.models import Author
from order.models import Order
from .forms import BookForm


def _filter_books(query: str, author_id: str):
    """Filter book queryset by search query and/or author ID."""
    books = Book.objects.prefetch_related('authors').all()

    if query:
        books = books.filter(Q(name__icontains=query) | Q(description__icontains=query))

    if author_id and author_id.isdigit():
        books = books.filter(authors__id=int(author_id))

    return books.distinct().order_by('id')


@login_required(login_url='login')
def book_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get('q', '').strip()
    author_id = request.GET.get('author_id', '').strip()

    books = _filter_books(query, author_id)
    authors = Author.objects.all().order_by('surname', 'name')

    return render(request, 'book/book_list.html', {
        'books': books,
        'authors': authors,
        'query': query,
        'selected_author_id': int(author_id) if author_id.isdigit() else '',
    })


@login_required(login_url='login')
def book_detail(request: HttpRequest, book_id: int) -> HttpResponse:
    book = get_object_or_404(Book.objects.prefetch_related('authors'), pk=book_id)
    return render(request, 'book/book_detail.html', {'book': book})


@librarian_required
def book_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = BookForm(request.POST)
        if form.is_valid():
            book = form.save()
            messages.success(request, f'Book "{book.name}" created successfully.')
            return redirect('book_list')
    else:
        form = BookForm()
    return render(request, 'book/book_create.html', {'form': form})


@librarian_required
def book_update(request: HttpRequest, book_id: int) -> HttpResponse:
    book = get_object_or_404(Book, pk=book_id)
    if request.method == 'POST':
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, f'Book "{book.name}" updated successfully.')
            return redirect('book_detail', book_id=book.id)
    else:
        form = BookForm(instance=book)
    return render(request, 'book/book_update.html', {'form': form, 'book': book})


@librarian_required
def books_by_user(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = get_object_or_404(CustomUser, pk=user_id)
    active_orders = Order.objects.filter(user=target_user, end_at__isnull=True).select_related('book')

    return render(request, 'book/books_by_user.html', {
        'target_user': target_user,
        'active_orders': active_orders,
    })

