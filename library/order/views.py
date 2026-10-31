from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from authentication.decorators import librarian_required, signin_required
from authentication.permissions import is_librarian
from book.models import Book

from . import services
from .forms import CancelForm, IssueForm, LendForm, OrderUpdateForm
from .models import BookUnavailableError, Order, Reservation, ReservationState


def _name(user) -> str:
    return f"{user.first_name} {user.last_name}"


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
    """Every loan starts with a librarian (FR-015): readers reserve on the book page,
    and librarians lend directly."""
    book = get_object_or_404(Book, pk=book_id)
    if is_librarian(request.user):
        return redirect(f"{reverse('order_lend')}?book={book.pk}")
    return redirect("book_detail", book_id=book.pk)


@librarian_required
def order_lend(request: HttpRequest) -> HttpResponse:
    """Lend directly, with or without a reservation (FR-016). A reservation the reader
    holds for the book is issued."""
    if request.method == "POST":
        form = LendForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                loan = services.lend(
                    request.user, data["reader"], data["book"], data["days"]
                )
            except services.ReservationRefused as refused:
                form.add_error(None, refused.message)
            else:
                messages.success(
                    request,
                    f"Lent “{loan.book.name}” to {_name(loan.user)}, due "
                    f"{services.local(loan.plated_end_at, services.DATE)}.",
                )
                return redirect("order_all")
    else:
        form = LendForm(
            initial={
                "book": request.GET.get("book"),
                "reader": request.GET.get("reader"),
            }
        )
    return render(request, "order/order_lend.html", {"form": form})


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
        Reservation.objects.filter(user=request.user).select_related("book", "loan"),
        now,
    )
    rows = [
        {
            "reservation": reservation,
            "state": ReservationState(reservation.effective_state(now)),
            "next_step": services.next_step(reservation, now),
        }
        for reservation in reservations
    ]
    return render(request, "order/reservation_my.html", {"rows": rows, "now": now})


@librarian_required
def reservation_desk(request: HttpRequest) -> HttpResponse:
    """Active reservations by deadline, with the reader, the book and the time left
    (FR-019)."""
    now = timezone.now()
    reservations = (
        Reservation.objects.filter(state=ReservationState.ACTIVE, expires_at__gt=now)
        .select_related("user", "book")
        .order_by("expires_at")
    )
    return render(
        request,
        "order/reservation_desk.html",
        {"reservations": reservations, "now": now},
    )


@librarian_required
def reservation_issue(request: HttpRequest, reservation_id: int) -> HttpResponse:
    """The loan period form, or why the reservation cannot be issued and what to do
    instead (FR-020)."""
    reservation = get_object_or_404(
        Reservation.objects.select_related("user", "book"), pk=reservation_id
    )
    now = timezone.now()
    refused = None
    if request.method == "POST":
        form = IssueForm(request.POST)
        if form.is_valid():
            try:
                loan = services.issue(
                    request.user, reservation, form.cleaned_data["days"]
                )
            except services.ReservationRefused as refusal:
                refused = refusal
            else:
                messages.success(
                    request,
                    f"Issued “{reservation.book.name}” to {_name(reservation.user)} "
                    f"as loan #{loan.pk}, due "
                    f"{services.local(loan.plated_end_at, services.DATE)}.",
                )
                return redirect("reservation_desk")
    else:
        form = IssueForm()
        refused = services.issue_refusal(
            reservation, reservation.user, reservation.book, now
        )
    return render(
        request,
        "order/reservation_issue.html",
        {"reservation": reservation, "form": form, "refusal": refused, "now": now},
    )


@signin_required
def reservation_cancel(request: HttpRequest, reservation_id: int) -> HttpResponse:
    """The reservation's reader cancels without a reason, and this page is their
    confirmation step. A librarian cancelling someone else's gives a reason, then
    confirms it on a second step (FR-017, FR-018, R17). Another reader's answers 404."""
    reservations = Reservation.objects.select_related("user", "book")
    if not is_librarian(request.user):
        reservations = reservations.filter(user=request.user)
    reservation = get_object_or_404(reservations, pk=reservation_id)
    own = reservation.user_id == request.user.pk
    back = "reservation_my" if own else "reservation_desk"
    now = timezone.now()
    confirming = False
    refused = None
    if request.method == "POST":
        form = CancelForm(request.POST, reason_required=not own)
        if form.is_valid() and (own or request.POST.get("confirm") == "yes"):
            try:
                services.cancel(request.user, reservation, form.cleaned_data["reason"])
            except services.ReservationRefused as refusal:
                refused = refusal
            else:
                book = reservation.book.name
                messages.success(
                    request,
                    (
                        f"Cancelled your reservation of “{book}”."
                        if own
                        else f"Cancelled the reservation of “{book}” for "
                        f"{_name(reservation.user)}. They will see your reason the next "
                        "time they open the site."
                    ),
                )
                return redirect(back)
        elif form.is_valid():
            # The reason, once more, before the reader sees it; or back to editing it.
            confirming = "edit" not in request.POST
    else:
        form = CancelForm(reason_required=not own)
        refused = services.cancel_refusal(
            reservation, now, librarian=is_librarian(request.user)
        )
    return render(
        request,
        "order/reservation_cancel.html",
        {
            "reservation": reservation,
            "form": form,
            "own": own,
            "back": back,
            "now": now,
            "confirming": confirming,
            "refusal": refused,
        },
    )


@signin_required
@require_POST
def reservation_notice_dismiss(
    request: HttpRequest, reservation_id: int
) -> HttpResponse:
    """Hide the library's cancellation notice; only its reader can (R15)."""
    reservation = get_object_or_404(Reservation, pk=reservation_id, user=request.user)
    if (
        reservation.state == ReservationState.CANCELLED
        and reservation.cancellation_seen_at is None
    ):
        reservation.cancellation_seen_at = timezone.now()
        reservation.save(update_fields=["cancellation_seen_at"])
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = reverse("reservation_my")
    return redirect(target)


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
