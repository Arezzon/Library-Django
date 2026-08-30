from django import forms
from library.forms_mixins import TailwindFormMixin
from .models import Order


class OrderCreateForm(TailwindFormMixin, forms.Form):
    days = forms.IntegerField(
        min_value=1,
        max_value=30,
        initial=14,
        label="Loan Duration (Days)",
        help_text="Choose loan period from 1 to 30 days (Standard: 14 days)."
    )


class OrderUpdateForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Order
        fields = ['plated_end_at', 'end_at']
        labels = {
            'plated_end_at': 'Planned Return Date & Time',
            'end_at': 'Actual Return Date & Time',
        }
        widgets = {
            'plated_end_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

