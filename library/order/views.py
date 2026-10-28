from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from authentication.decorators import librarian_required, signin_required
from book.models import Book

from . import services
from .forms import OrderCreateForm, OrderUpdateForm
from .models import BookUnavailableError, Order, Reservation, ReservationState


def _close_order(request: HttpRequest, order_id: int) -> None:
    """Close active order by recording end_at timestamp."""
    order = get_object_or_404(Order, pk=order_id)
    if order.end_at is None:
        order.end_at = timezone.now()
        order.save()
        messages.success(request, f"Order #{order.id} closed (Book returned).")
    else:
        messages.info(request, f"Order #{order.id} was already closed.")


@signin_required
def order_my(request: HttpRequest) -> HttpResponse:
    orders = (
        Order.objects.filter(user=request.user)
        .select_related("book")
        .order_by("-created_at")
    )
    return render(request, "order/order_my.html", {"orders": orders})


@librarian_required
def order_all(request: HttpRequest) -> HttpResponse:
    orders = Order.objects.select_related("user", "book").all().order_by("-created_at")
    return render(request, "order/order_all.html", {"orders": orders})


@signin_required
def order_create(request: HttpRequest, book_id: int) -> HttpResponse:
    book = get_object_or_404(Book, pk=book_id)
    refused = services.eligibility(request.user, book, timezone.now(), lending=True)
    if refused is not None:
        messages.error(request, refused.message)
        return redirect("book_detail", book_id=book.id)
    if request.method == "POST":
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            try:
                # A reservation the reader holds for this book is issued (FR-061).
                services.lend(
                    request.user, request.user, book, form.cleaned_data["days"]
                )
            except services.ReservationRefused as refused:
                messages.error(request, refused.message)
                return redirect("book_detail", book_id=book.id)
            messages.success(request, f'Order for "{book.name}" created successfully!')
            return redirect("order_my")
    else:
        form = OrderCreateForm()
    return render(request, "order/order_create.html", {"book": book, "form": form})


@signin_required
@require_POST
def reserve(request: HttpRequest, book_id: int) -> HttpResponse:
    book = get_object_or_404(Book, pk=book_id)
    try:
        reservation = services.reserve(request.user, book)
    except services.ReservationRefused as refused:
        messages.error(request, refused.message)
        return redirect("book_detail", book_id=book.id)
    messages.success(
        request,
        f"Reserved “{book.name}”. Collect it from a librarian before "
        f"{services.local(reservation.expires_at)}.",
    )
    return redirect("reservation_my")


@signin_required
def reservation_my(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    reservations = services.listed(
        Reservation.objects.filter(user=request.user).select_related("book"), now
    )
    rows = [
        {
            "reservation": reservation,
            "state": ReservationState(reservation.effective_state(now)),
            "next_step": services.next_step(reservation, now),
        }
        for reservation in reservations
    ]
    return render(request, "order/reservation_my.html", {"rows": rows})


@librarian_required
def order_update(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(Order, pk=order_id)
    if request.method == "POST":
        form = OrderUpdateForm(request.POST, instance=order)
        if form.is_valid():
            try:
                form.save()
            except BookUnavailableError as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, f"Order #{order.id} updated successfully.")
                return redirect("order_all")
    else:
        form = OrderUpdateForm(instance=order)
    return render(request, "order/order_update.html", {"form": form, "order": order})


@librarian_required
def order_close(request: HttpRequest, order_id: int) -> HttpResponse:
    if request.method == "POST":
        _close_order(request, order_id)
    return redirect("order_all")
