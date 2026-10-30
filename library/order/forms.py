from django import forms

from authentication.models import CustomUser
from book.models import Book
from library.forms_mixins import TailwindFormMixin

from .models import Order
from .services import REASON_LENGTH, REASON_RULE


class IssueForm(TailwindFormMixin, forms.Form):
    days = forms.IntegerField(
        min_value=1,
        max_value=30,
        initial=14,
        label="Loan Duration (Days)",
        help_text="Choose loan period from 1 to 30 days (Standard: 14 days).",
    )


class LendForm(IssueForm):
    """A loan a librarian starts at the desk, with or without a reservation (FR-016)."""

    reader = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(is_active=True).order_by(
            "last_name", "first_name", "email"
        )
    )
    book = forms.ModelChoiceField(queryset=Book.objects.order_by("name"))
    field_order = ["reader", "book", "days"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reader"].label_from_instance = (
            lambda user: f"{user.first_name} {user.last_name} ({user.email})"
        )


class CancelForm(TailwindFormMixin, forms.Form):
    """The reason is required when a librarian cancels someone else's reservation; the
    reader sees it (FR-017)."""

    reason = forms.CharField(
        max_length=REASON_LENGTH,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="The reader sees this reason the next time they open the site.",
        error_messages={"required": REASON_RULE},
    )

    def __init__(self, *args, reason_required=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].required = reason_required


class OrderUpdateForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Order
        fields = ["plated_end_at", "end_at"]
        labels = {
            "plated_end_at": "Planned Return Date & Time",
            "end_at": "Actual Return Date & Time",
        }
        widgets = {
            "plated_end_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
