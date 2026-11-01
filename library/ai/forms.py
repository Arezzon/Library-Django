from django import forms

from .services import MAX_QUERY_LENGTH


class AssistantQuestionForm(forms.Form):
    intent = forms.ChoiceField(
        label="Що шукаємо?",
        choices=(
            ("auto", "Визначити за короткою командою"),
            ("title", "Книгу за назвою"),
            ("author", "Автора"),
            ("availability", "Наявність книги"),
        ),
        initial="auto",
        error_messages={
            "invalid_choice": "Оберіть назву, автора, наявність або коротку команду.",
            "required": "Оберіть тип пошуку.",
        },
        widget=forms.Select(attrs={"class": "w-full border rounded p-2"}),
    )
    q = forms.CharField(
        label="Ваше запитання",
        required=False,
        max_length=MAX_QUERY_LENGTH,
        widget=forms.Textarea(
            attrs={
                "class": "w-full border rounded p-2",
                "rows": 3,
                "maxlength": MAX_QUERY_LENGTH,
                "autocomplete": "off",
                "aria-describedby": "question-help question-errors",
            }
        ),
        error_messages={"max_length": "Скоротіть запит до 256 символів."},
    )
