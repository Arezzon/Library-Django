from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from authentication.decorators import librarian_required

from .forms import AuthorForm
from .models import Author


def _delete_author(request: HttpRequest, author_id: int) -> None:
    """Attempt to delete an author if not attached to any books."""
    author = Author.get_by_id(author_id)
    if not author:
        messages.error(request, "Author not found.")
        return

    refusal = author.deletion_refusal()
    if refusal:
        messages.error(request, refusal)
    else:
        Author.delete_by_id(author_id)
        messages.success(
            request,
            f'Author "{author.name} {author.surname}" was successfully deleted.',
        )


@librarian_required
def author_list(request: HttpRequest) -> HttpResponse:
    authors = Author.objects.prefetch_related("books").all().order_by("id")
    return render(request, "author/author_list.html", {"authors": authors})


@librarian_required
def author_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AuthorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Author created successfully!")
            return redirect("author_list")
    else:
        form = AuthorForm()
    return render(request, "author/author_create.html", {"form": form})


@librarian_required
def author_update(request: HttpRequest, author_id: int) -> HttpResponse:
    author = get_object_or_404(Author, pk=author_id)
    if request.method == "POST":
        form = AuthorForm(request.POST, instance=author)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Author "{author.name} {author.surname}" was successfully updated!',
            )
            return redirect("author_list")
    else:
        form = AuthorForm(instance=author)
    return render(
        request, "author/author_update.html", {"form": form, "author": author}
    )


@librarian_required
def author_delete(request: HttpRequest, author_id: int) -> HttpResponse:
    if request.method == "POST":
        _delete_author(request, author_id)
    return redirect("author_list")
