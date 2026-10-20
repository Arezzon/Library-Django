from django.apps import AppConfig


class BookConfig(AppConfig):
    name = "book"

    def ready(self):
        from . import checks  # noqa: F401  (registers the system checks)
