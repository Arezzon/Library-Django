"""What the templates show people (spec Story 6, FR-043 and FR-044).

The time zone check reads the template files, so it covers pages that no test opens.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from book.models import Book
from book.testing import FakeEncoderMixin

from .models import ROLE_LIBRARIAN
from .test_access import account

TEMPLATES = sorted(Path(settings.BASE_DIR).glob("*/templates/**/*.html"))
BASE_TEMPLATE = Path(settings.BASE_DIR, "library", "templates", "base.html")
VOID_ELEMENTS = {
    "area",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "wbr",
}


class StatusRegions(HTMLParser):
    """Counts the elements with role="status" and collects the text inside them."""

    def __init__(self, page):
        super().__init__()
        self.count = 0
        self.depth = 0
        self.texts = []
        self.feed(page)
        self.text = " ".join(" ".join(self.texts).split())

    def handle_starttag(self, tag, attrs):
        if self.depth:
            self.depth += tag not in VOID_ELEMENTS
        elif ("role", "status") in attrs:
            self.count += 1
            self.depth = 1

    def handle_endtag(self, tag):
        self.depth = max(self.depth - 1, 0)

    def handle_data(self, data):
        if self.depth:
            self.texts.append(data)


# Format characters of Django's date filter that show a time, and those that show the zone.
TIME_CHARACTERS = set("HGiAaP")
ZONE_CHARACTERS = set("TeO")
DATE_FILTER = re.compile(r"""\|date:\s*(["'])(.*?)\1""")


def format_characters(date_format):
    """The characters the date filter reads as format characters, without escaped ones."""
    characters = set()
    escaped = False
    for character in date_format:
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        else:
            characters.add(character)
    return characters


def times_without_zone(text):
    """Each date filter in the text that shows a time without its zone, with its line."""
    found = []
    for match in DATE_FILTER.finditer(text):
        characters = format_characters(match.group(2))
        if characters & TIME_CHARACTERS and not characters & ZONE_CHARACTERS:
            found.append((text.count("\n", 0, match.start()) + 1, match.group(0)))
    return found


class TimeZoneTests(SimpleTestCase):
    def test_the_check_tells_a_time_with_its_zone_from_one_without(self):
        self.assertEqual(times_without_zone('{{ a|date:"j M Y, H:i T" }}'), [])
        self.assertEqual(times_without_zone("{{ a|date:'Y-m-d' }}"), [])
        self.assertEqual(times_without_zone('{{ a|date:"\\H\\o\\u\\r" }}'), [])
        self.assertEqual(
            times_without_zone("{{ a|date:'d M H:i:s' }}"), [(1, "|date:'d M H:i:s'")]
        )
        self.assertEqual(
            times_without_zone('x\n{{ a|date:"g A" }}'), [(2, '|date:"g A"')]
        )

    def test_every_time_shown_says_its_zone(self):
        base = Path(settings.BASE_DIR, "library", "templates", "base.html")
        self.assertIn(base, TEMPLATES)
        found = [
            f"{template.relative_to(settings.BASE_DIR).as_posix()}:{line} {date_filter}"
            for template in TEMPLATES
            for line, date_filter in times_without_zone(template.read_text("utf-8"))
        ]
        self.assertEqual(found, [])


class LayoutTests(FakeEncoderMixin, TestCase):
    """The shared layout in base.html (T155)."""

    def page(self, path="/"):
        return self.client.get(path).content.decode()

    def test_a_skip_link_leads_to_the_main_content(self):
        page = self.page("/authentication/login/")
        first_link = re.search(r"<a\b[^>]*>", page[page.index("<body") :]).group(0)
        self.assertIn('href="#main"', first_link)
        self.assertIn("Skip to main content", page)
        self.assertIn('<main id="main"', page)

    def test_links_and_buttons_show_where_the_keyboard_focus_is(self):
        styles = BASE_TEMPLATE.read_text("utf-8")
        components = ["nav-link", "mobile-nav-link", "btn-logout"]
        components += [f"btn-{kind}" for kind in ("primary", "secondary", "danger")]
        components += [f"btn-sm-{kind}" for kind in ("primary", "secondary", "danger")]
        components += ["btn-sm-success"]
        for component in components:
            rule = re.search(rf"\.{component} \{{\s*@apply ([^;]*);", styles).group(1)
            self.assertIn("focus-visible:ring-2", rule.split(), component)

    def test_messages_appear_once_in_the_one_status_region(self):
        self.client.force_login(account("desk@example.com", ROLE_LIBRARIAN))
        book = Book.objects.create(name="Forest Song", count=1)
        response = self.client.post(
            "/author/create/",
            {"name": "Lesya", "surname": "Ukrainka", "books": [book.pk]},
            follow=True,
        )
        self.assertEqual(response.redirect_chain, [("/author/", 302)])
        page = response.content.decode()
        regions = StatusRegions(page)
        self.assertEqual(regions.count, 1)
        self.assertIn("Author “Lesya Ukrainka” added.", regions.text)
        self.assertEqual(page.count("Author “Lesya Ukrainka” added."), 1)

    def test_a_page_without_its_own_messages_shows_them_too(self):
        response = self.client.post(
            "/authentication/register/",
            {
                "first_name": "Ann",
                "middle_name": "M",
                "last_name": "Reader",
                "email": "ann@example.com",
                "password": "layout-check-password-42",
                "confirm_password": "layout-check-password-42",
            },
            follow=True,
        )
        self.assertEqual(response.redirect_chain, [("/", 302)])
        self.assertIn(
            "Welcome to the library.", StatusRegions(response.content.decode()).text
        )

    def test_every_page_says_which_zone_its_times_are_in(self):
        page = self.page("/authentication/login/")
        self.assertEqual(page.count("Times are shown in Kyiv time (EET/EEST)."), 1)

    def test_a_signed_in_reader_reaches_their_profile_from_every_page(self):
        reader = account("profile@example.com")
        self.client.force_login(reader)
        links = re.findall(
            rf'<a href="/authentication/users/{reader.pk}/"[^>]*>', self.page()
        )
        self.assertEqual(len(links), 2)  # the desktop and the mobile menu


class FormTests(FakeEncoderMixin, TestCase):
    """Labels, help, errors and values in includes/form_snippet.html (T156, FR-043)."""

    def register(self, **data):
        response = self.client.post(
            "/authentication/register/", {"first_name": "Ann", **data}
        )
        return response.content.decode()

    def librarian(self):
        self.client.force_login(account("books@example.com", ROLE_LIBRARIAN))

    def test_errors_are_tied_to_their_fields_and_say_how_to_fix_them(self):
        page = self.register(email="")
        email = re.search(r'<input [^>]*name="email"[^>]*>', page).group(0)
        self.assertIn('aria-invalid="true"', email)
        self.assertIn('aria-describedby="id_email_error"', email)
        self.assertRegex(page, r'<div id="id_email_error"')
        error = re.search(r'<div id="id_email_error"[^>]*>(.*?)</div>', page, re.S)
        self.assertIn("Enter email address.", error.group(1))

    def test_a_form_with_errors_keeps_what_was_typed(self):
        page = self.register(email="", last_name="Reader")
        self.assertRegex(page, r'<input [^>]*name="first_name" value="Ann"')
        self.assertRegex(page, r'<input [^>]*name="last_name" value="Reader"')

    def test_a_page_with_form_errors_says_so_in_its_title(self):
        self.assertRegex(self.register(email=""), r"<title>Error: ")
        self.assertNotIn(
            "<title>Error: ",
            self.client.get("/authentication/register/").content.decode(),
        )

    def test_required_fields_are_marked(self):
        page = self.client.get("/authentication/register/").content.decode()
        self.assertEqual(
            page.count("Fields marked with an asterisk (*) are required."), 1
        )
        label = re.search(
            r'<label for="id_email"[^>]*>(.*?)</label>', page, re.S
        ).group(1)
        self.assertIn('<span class="text-rose-700" aria-hidden="true">*</span>', label)
        self.assertRegex(page, r'<input [^>]*name="email"[^>]*required')

    def test_help_text_is_tied_to_its_field(self):
        self.librarian()
        page = self.client.get("/book/create/").content.decode()
        authors = re.search(r'<select [^>]*name="authors"[^>]*>', page).group(0)
        self.assertIn('aria-describedby="id_authors_helptext"', authors)
        self.assertRegex(page, r'<p id="id_authors_helptext"[^>]*>Hold down')

    def test_a_number_out_of_range_names_the_field_and_the_limit(self):
        self.librarian()
        response = self.client.post("/book/create/", {"name": "Spare", "count": "-1"})
        self.assertContains(response, "Total Copies Available must be 0 or more.")
        self.assertFalse(Book.objects.filter(name="Spare").exists())

    def test_a_failed_sign_in_says_what_to_do_and_keeps_the_email(self):
        account("signin@example.com")
        response = self.client.post(
            "/authentication/login/",
            {"email": "signin@example.com", "password": "wrong"},
        )
        page = response.content.decode()
        self.assertIn(
            "The email or password is not right. Check both and try again.", page
        )
        self.assertRegex(page, r"<title>Error: ")
        self.assertRegex(page, r'<input [^>]*name="email" value="signin@example.com"')
