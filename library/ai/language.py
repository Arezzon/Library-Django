"""Bounded Ukrainian/English catalog grammar, independent of database and models."""

import re
from dataclasses import dataclass

PREFIXES = {
    "книга": "title",
    "назва": "title",
    "book": "title",
    "title": "title",
    "автор": "author",
    "author": "author",
    "наявність": "availability",
    "доступність": "availability",
    "availability": "availability",
}


@dataclass(frozen=True)
class CatalogQuery:
    intent: str
    text: str = ""
    available_only: bool = False
    followup: bool = False
    single: bool = False
    literal: bool = False


def _match(pattern, text):
    return re.fullmatch(pattern, text, re.IGNORECASE)


def parse_query(query, intent="auto"):
    query = " ".join(query.split())
    if intent != "auto":
        return CatalogQuery(intent, query, literal=True)
    prefix, separator, rest = query.partition(":")
    if separator and prefix.casefold() in PREFIXES:
        return CatalogQuery(PREFIXES[prefix.casefold()], rest.strip(), literal=True)
    if separator and prefix.casefold() in {
        "бронювання",
        "видача",
        "reserve",
        "borrow",
        "delete",
        "cancel",
        "return",
    }:
        return CatalogQuery("clarify")
    text = query.strip().rstrip("?!. ").strip('"«»“”')
    if not text:
        return CatalogQuery("clarify")
    # A request to mutate the library never becomes a read or a booking command.
    if re.match(
        r"^(?:забронюй|забронювати|видали|створи|поверни|скасуй|reserve|delete|create|return|cancel|borrow)\b",
        text,
        re.I,
    ):
        return CatalogQuery("clarify")
    available = re.search(
        r"\b(?:доступн\w*|наявност\w*|available|in stock)\b", text, re.I
    )
    reference = re.search(
        r"\b(?:з них|із них|ці|них|them|these|those|ones|it|ця|вона|this one)\b",
        text,
        re.I,
    )
    if available and reference:
        single = bool(re.search(r"\b(?:it|ця|вона|this one)\b", text, re.I))
        return CatalogQuery(
            "availability", available_only=True, followup=True, single=single
        )
    recommendation = bool(
        re.search(r"\b(?:порадь|порекомендуй|recommend|suggest)\b", text, re.I)
    )
    # Strip only the grammatical request wrapper, never arbitrary words in a title.
    text = re.sub(r"^(?:(?:будь ласка|please)[,\s]+)", "", text, flags=re.I)
    text = re.sub(r"^(?:can you|could you|чи можеш|можеш)\s+", "", text, flags=re.I)
    text = re.sub(
        r"^(?:знайди|знайдіть|покажи|покажіть|порадь|порекомендуй|find|show|recommend|suggest)(?:\s+(?:me|мені))?\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^(?:хочу почитати|хочу прочитати|i want to read|i would like to read)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"[,\s]+(?:будь ласка|please)$", "", text, flags=re.I)
    for pattern in (
        r"(?:чи\s+)?є\s+(?:у вас\s+|в бібліотеці\s+)?(?:в наявності\s+|у наявності\s+)?(.+)",
        r"(?:чи\s+)?(?:доступна|доступний|доступне)\s+(?:книга\s+)?(.+)",
        r"(?:is|are)\s+(.+?)\s+(?:available|in stock)",
        r"do you have\s+(.+)",
        r"(?:у|в) вас є\s+(.+)",
        r"(?:чи\s+)?(?:книга\s+)?(.+?)\s+(?:доступна|доступний|доступне)",
        r"can i (?:borrow|read)\s+(.+)",
        r"чи можна (?:взяти|прочитати)\s+(.+)",
    ):
        match = _match(pattern, text)
        if match:
            target = re.sub(r"^(?:книг[ау]|the book|book)\s+", "", match[1], flags=re.I)
            nested = parse_query(target)
            if nested.intent in ("author", "topic"):
                return CatalogQuery(nested.intent, nested.text, available_only=True)
            return CatalogQuery("availability", target.strip('"«»“”'))
    # Plural availability requests filter a collection; a named title still reports zero stock.
    available_only = bool(available)
    if available_only:
        text = re.sub(r"\b(?:у|в)\s+наявності\b", "", text, flags=re.I)
        text = re.sub(r"\bare\b", "", text, flags=re.I)
        text = re.sub(
            r"\b(?:доступн\w*|наявност\w*|available|in stock|зараз|нині|currently|now)\b",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(r"^(?:а\s+)?(?:які|which|what)\s+", "", text, flags=re.I)
        text = " ".join(text.split())
    topic = _match(
        r"(?:(?:a|some|any|the)\s+)?(?:книг\w*|книж\w*|щось|books?|novels?|something)\s+(?:про|на тему|about|on)\s+(.+)",
        text,
    )
    if topic:
        return CatalogQuery("topic", topic[1], available_only)
    for pattern in (
        r"(?:(?:усі|всі|all|the)\s+)?(?:твори|творів|книги|книжки|романи|вірші)\s+(?:(?:автора|авторки|письменника|письменниці)\s+)?(.+)",
        r"(?:(?:all|the)\s+)?(?:books|works|novels|poems)(?:\s+written)?\s+(?:by|of)\s+(.+)",
        r"(.+?)[’']s\s+(?:books|works|novels|poems)",
        r"(?:автор|author)\s+(.+)",
        r"що\s+(?:написав|написала)\s+(.+)",
        r"what did\s+(.+?)\s+write",
    ):
        match = _match(pattern, text)
        if match:
            return CatalogQuery("author", match[1], available_only)
    if _match(r"(?:книги|книжки|books|the books)", text):
        return CatalogQuery(
            "availability" if available_only else "clarify",
            available_only=available_only,
        )
    if recommendation:
        if text == query or len(text) < 3:
            return CatalogQuery("clarify")
        subject = re.sub(r"^(?:a|some|any|the)\s+", "", text, flags=re.I)
        subject = re.sub(r"\s+(?:books?|novels?)$", "", subject, flags=re.I)
        return CatalogQuery("topic", subject, available_only)
    if re.match(
        r"^(?:яка погода|розкажи анекдот|what is the weather|tell me a joke|write me)\b",
        text,
        re.I,
    ):
        return CatalogQuery("clarify")
    for pattern in (r"хто (?:написав|написала)\s+(.+)", r"who wrote\s+(.+)"):
        match = _match(pattern, text)
        if match:
            return CatalogQuery("title", match[1].strip('"«»“”'))
    text = re.sub(r"^(?:книг[ау]|книжку|the book|a book|book)\s+", "", text, flags=re.I)
    return CatalogQuery("title", text.strip('"«»“”'), available_only)
