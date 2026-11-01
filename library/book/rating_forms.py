from django import forms

from .rating_rules import MAX_RATING, MIN_RATING


class BookRatingForm(forms.Form):
    value = forms.TypedChoiceField(
        label="Your rating",
        coerce=int,
        choices=[("", "Choose a rating")]
        + [
            (number, f"{number} / {MAX_RATING}")
            for number in range(MIN_RATING, MAX_RATING + 1)
        ],
        widget=forms.Select(
            attrs={
                "class": "border rounded p-2",
                "aria-describedby": "rating-help rating-errors",
            }
        ),
        error_messages={
            "required": "Choose a rating from 1 to 5.",
            "invalid_choice": "Choose a rating from 1 to 5.",
        },
    )
