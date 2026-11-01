"""Grant or remove the administrator role on the server (FR-063, research R26).

The web, the API and the admin site never grant the administrator role: the operator
runs this command in the web container. Outside a request, the change is audited with
channel "command".
"""

from django.core.management.base import BaseCommand, CommandError

from audit.services import account_label
from authentication.models import ROLE_ADMINISTRATOR, ROLE_LIBRARIAN, CustomUser


class Command(BaseCommand):
    help = (
        "Make an existing account an administrator, or with --remove make an "
        "administrator a librarian. The account is kept either way."
    )

    def add_arguments(self, parser):
        parser.add_argument("email", help="The account's email address.")
        parser.add_argument(
            "--remove",
            action="store_true",
            help="Make the administrator a librarian instead.",
        )

    def handle(self, *args, **options):
        email = CustomUser.objects.normalize_email(options["email"])
        account = CustomUser.objects.filter(email=email).first()
        if account is None:
            raise CommandError("No account has this email.")
        label = account_label(account)
        if options["remove"] and not account.is_administrator:
            self.stdout.write(f"{label} is not an administrator. Nothing changed.")
            return
        if not options["remove"] and account.is_administrator:
            self.stdout.write(f"{label} is already an administrator. Nothing changed.")
            return
        account.role = ROLE_LIBRARIAN if options["remove"] else ROLE_ADMINISTRATOR
        account.save()
        role = "a librarian" if options["remove"] else "an administrator"
        self.stdout.write(f"{label} is now {role}.")
