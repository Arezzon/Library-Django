from django import forms

from .services import MAX_QUERY_LENGTH


class AssistantQuestionForm(forms.Form):
    intent = forms.ChoiceField(
        label="Search by",
        required=False,
        choices=(
            ("auto", "Detect automatically"),
            ("title", "Book title"),
            ("author", "Author"),
            ("availability", "Availability"),
        ),
        initial="auto",
        error_messages={
            "invalid_choice": "Choose a title, author, availability or automatic search.",
            "required": "Choose a search type.",
        },
        widget=forms.Select(attrs={"class": "field"}),
    )
    q = forms.CharField(
        label="Your question",
        required=False,
        max_length=MAX_QUERY_LENGTH,
        widget=forms.Textarea(
            attrs={
                "class": "field",
                "rows": 2,
                "maxlength": MAX_QUERY_LENGTH,
                "autocomplete": "off",
                "placeholder": "Знайди твори Шевченка / Find books by Shevchenko",
                "aria-describedby": "question-help question-errors",
            }
        ),
        error_messages={"max_length": "Keep your question within 256 characters."},
    )

    def clean_intent(self):
        return self.cleaned_data["intent"] or "auto"
