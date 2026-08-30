from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect


def home(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("login")
    return render(request, "home.html")
