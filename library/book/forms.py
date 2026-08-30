from django import forms
from library.forms_mixins import TailwindFormMixin
from .models import Book
from author.models import Author


class BookForm(TailwindFormMixin, forms.ModelForm):
    authors = forms.ModelMultipleChoiceField(
        queryset=Author.objects.all(),
        required=False,
        label="Authors",
        help_text="Hold down 'Ctrl' (or 'Cmd' on Mac) to select multiple authors."
    )

    class Meta:
        model = Book
        fields = ['name', 'description', 'count', 'authors']
        labels = {
            'name': 'Book Title',
            'description': 'Description',
            'count': 'Total Copies Available',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Brief description of the book...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['authors'].initial = self.instance.authors.all()

    def save(self, commit=True):
        book = super().save(commit=commit)
        if commit:
            book.authors.set(self.cleaned_data['authors'])
        return book
