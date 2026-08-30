from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages

from .models import CustomUser, ROLE_VISITOR, ROLE_LIBRARIAN
from .forms import RegistrationForm, LoginForm, UserUpdateForm
from .decorators import librarian_required, librarian_or_owner_required


def index(request: HttpRequest) -> HttpResponse:
    return render(request, 'authentication/index.html')


def register(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(request, "Registration successful! Welcome to the library.")
            return redirect('home')
    else:
        form = RegistrationForm()
    return render(request, 'authentication/register.html', {'form': form})


def login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('home')
    error = None
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, username=email, password=password)
            if user is not None:
                auth_login(request, user)
                return redirect('home')
            else:
                error = "Invalid email or password."
    else:
        form = LoginForm()
    return render(request, 'authentication/login.html', {'form': form, 'error': error})


@librarian_or_owner_required(user_id_param='user_id')
def user_update(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = get_object_or_404(CustomUser, pk=user_id)
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=target_user)
        if form.is_valid():
            form.save()
            messages.success(request, f'User profile #{target_user.id} updated successfully.')
            return redirect('user_detail', user_id=target_user.id)
    else:
        form = UserUpdateForm(instance=target_user)
    return render(request, 'authentication/user_update.html', {'form': form, 'target_user': target_user})


@librarian_required
def user_list(request: HttpRequest) -> HttpResponse:
    users = CustomUser.objects.all().order_by('id')
    return render(request, 'authentication/user_list.html', {'users': users})


@librarian_or_owner_required(user_id_param='user_id')
def user_detail(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = get_object_or_404(CustomUser, pk=user_id)
    return render(request, 'authentication/user_detail.html', {'target_user': target_user})


def logout(request: HttpRequest) -> HttpResponse:
    auth_logout(request)
    return redirect("login")