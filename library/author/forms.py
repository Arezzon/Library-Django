from django import forms
from library.forms_mixins import TailwindFormMixin
from .models import Author


class AuthorForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Author
        fields = ['name', 'surname', 'patronymic', 'books']
        labels = {
            'name': "First Name",
            'surname': 'Last Name',
            'patronymic': 'Middle Name (Patronymic)',
            'books': 'Attached Books',
        }
        help_texts = {
            'books': 'Hold down "Ctrl" (or "Cmd" on Mac) to select multiple books.',
        }

