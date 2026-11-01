from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import librarian_or_owner_required, librarian_required
from .forms import LoginForm, ProfileForm, RegistrationForm, UserUpdateForm
from .models import CustomUser
from .services import (
    check_changes,
    may_change_account,
    may_change_role,
    may_change_status,
    update_account,
)


def index(request: HttpRequest) -> HttpResponse:
    return redirect("home" if request.user.is_authenticated else "login")


def register(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(
                request, "Registration successful! Welcome to the library."
            )
            return redirect("home")
    else:
        form = RegistrationForm()
    return render(request, "authentication/register.html", {"form": form})


def login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=email, password=password)
            if user is not None:
                auth_login(request, user)
                return redirect("home")
            form.add_error(
                None, "The email or password is not right. Check both and try again."
            )
    else:
        form = LoginForm()
    return render(request, "authentication/login.html", {"form": form})


def account_form(actor, account, data=None):
    """The fields ``actor`` may change on ``account``: a reader's own names, or a
    librarian's form, which has the role only for administrators."""
    if may_change_role(actor, account) or may_change_status(actor, account):
        return UserUpdateForm(data, instance=account, actor=actor)
    return ProfileForm(data, instance=account)


@librarian_or_owner_required(user_id_param="user_id")
def user_update(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = get_object_or_404(CustomUser, pk=user_id)
    if not may_change_account(request.user, target_user):
        raise PermissionDenied
    if request.method == "POST":
        # A role or status sent by someone who may not change it is refused whole.
        check_changes(request.user, target_user, request.POST)
        form = account_form(request.user, target_user, request.POST)
        if form.is_valid():
            update_account(request.user, target_user, form.cleaned_data)
            messages.success(request, f"Changes to {target_user.email} saved.")
            return redirect("user_detail", user_id=target_user.id)
    else:
        form = account_form(request.user, target_user)
    return render(
        request,
        "authentication/user_update.html",
        {"form": form, "target_user": target_user},
    )


@librarian_required
def user_list(request: HttpRequest) -> HttpResponse:
    users = CustomUser.objects.all().order_by("id")
    return render(request, "authentication/user_list.html", {"users": users})


@librarian_or_owner_required(user_id_param="user_id")
def user_detail(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = get_object_or_404(CustomUser, pk=user_id)
    context = {
        "target_user": target_user,
        "may_edit": may_change_account(request.user, target_user),
    }
    if request.user.is_librarian:
        from events.analytics import build_analytics_context

        context.update(build_analytics_context(request, user=target_user))
        context["profile_activity"] = True
    return render(request, "authentication/user_detail.html", context)


def logout(request: HttpRequest) -> HttpResponse:
    auth_logout(request)
    return redirect("login")
