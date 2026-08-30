import datetime
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from authentication.decorators import librarian_required
from .models import Order
from book.models import Book
from .forms import OrderCreateForm, OrderUpdateForm


def _check_borrow_eligibility(request: HttpRequest, book: Book) -> bool:
    """Check if the user is eligible to borrow this book."""
    if book.available_count <= 0:
        messages.error(request, f'Book "{book.name}" is currently unavailable.')
        return False
    if Order.objects.filter(user=request.user, book=book, end_at__isnull=True).exists():
        messages.error(request, f'You already have an active order for "{book.name}".')
        return False
    return True


def _close_order(request: HttpRequest, order_id: int) -> None:
    """Close active order by recording end_at timestamp."""
    order = get_object_or_404(Order, pk=order_id)
    if order.end_at is None:
        order.end_at = timezone.now()
        order.save()
        messages.success(request, f'Order #{order.id} closed (Book returned).')
    else:
        messages.info(request, f'Order #{order.id} was already closed.')


@login_required(login_url='login')
def order_my(request: HttpRequest) -> HttpResponse:
    orders = Order.objects.filter(user=request.user).select_related('book').order_by('-created_at')
    return render(request, 'order/order_my.html', {'orders': orders})


@librarian_required
def order_all(request: HttpRequest) -> HttpResponse:
    orders = Order.objects.select_related('user', 'book').all().order_by('-created_at')
    return render(request, 'order/order_all.html', {'orders': orders})


@login_required(login_url='login')
def order_create(request: HttpRequest, book_id: int) -> HttpResponse:
    book = get_object_or_404(Book, pk=book_id)
    if not _check_borrow_eligibility(request, book):
        return redirect('book_detail', book_id=book.id)
    if request.method == 'POST':
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            days_count = form.cleaned_data['days']
            plated_end_at = timezone.now() + datetime.timedelta(days=days_count)
            order = Order.create(user=request.user, book=book, plated_end_at=plated_end_at)
            if order:
                messages.success(request, f'Order for "{book.name}" created successfully!')
                return redirect('order_my')
            else:
                messages.error(request, 'Could not create order. Please try again.')
    else:
        form = OrderCreateForm()
    return render(request, 'order/order_create.html', {'book': book, 'form': form})


@librarian_required
def order_update(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(Order, pk=order_id)
    if request.method == 'POST':
        form = OrderUpdateForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, f'Order #{order.id} updated successfully.')
            return redirect('order_all')
    else:
        form = OrderUpdateForm(instance=order)
    return render(request, 'order/order_update.html', {'form': form, 'order': order})


@librarian_required
def order_close(request: HttpRequest, order_id: int) -> HttpResponse:
    if request.method == 'POST':
        _close_order(request, order_id)
    return redirect('order_all')

