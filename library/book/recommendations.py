"""Private, deterministic content-based recommendations using stored embeddings."""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.utils import timezone
from pgvector.django import CosineDistance

from authentication.permissions import is_signed_in
from events.models import EventType

from . import embeddings
from .embedding_config import resolve
from .embeddings import normalized_vector
from .models import BookEmbedding
from .recommendation_data import available_candidates, fallback_candidates, read_history

DEFAULT_LIMIT = 10
MAX_LIMIT = 20
SEARCH_WEIGHT = 1


FALLBACK_REASON = "Доступна книга із запасного списку рекомендацій."
PROFILE_REASON = "Рекомендовано за сукупністю ваших інтересів."
BOOK_REASONS = {
    EventType.BOOK_VIEW: "Рекомендовано, бо ви переглядали «{title}».",
    EventType.BOOK_CLICK: "Рекомендовано, бо ви цікавилися книгою «{title}».",
    EventType.BORROW_INTENT: "Рекомендовано, бо ви хотіли взяти «{title}».",
    EventType.ORDER_CREATED: "Рекомендовано, бо ви брали в бібліотеці «{title}».",
    EventType.ORDER_RETURNED: "Рекомендовано, бо ви повернули «{title}».",
}


@dataclass(frozen=True)
class _Signal:
    vector: list[float]
    weight: int
    reason: str


def _reason(book, signals):
    """Name the largest positive weighted contribution to this candidate.

    Normalizing the profile divides every contribution by the same positive
    constant, so this uses exactly the signal weights of the ranking. Stable
    source order breaks equal contributions. This is one main reason, not an
    exhaustive explanation or a claim that a borrowed book was actually read.
    """
    try:
        candidate = normalized_vector(book.embedding.vector)
    except ValueError:
        return PROFILE_REASON
    best, contribution = PROFILE_REASON, 0.0
    for signal in signals:
        score = signal.weight * sum(
            x * y for x, y in zip(candidate, signal.vector, strict=True)
        )
        if score > contribution:
            best, contribution = signal.reason, score
    return best


def _profile(user, now):
    """At most 200 recent own events, including three distinct text searches."""
    history = read_history(user, now=now)
    weights = {signal.book_id: signal.weight for signal in history.books}
    actions = {signal.book_id: signal.event_type for signal in history.books}
    queries = history.searches
    spec = resolve()
    vectors = BookEmbedding.objects.filter(
        book_id__in=weights, model=spec.repository, model_revision=spec.tag
    ).order_by("book_id")
    total = [0.0] * spec.dimensions
    seeds = []
    signals = []
    for embedding in vectors.select_related("book").only(
        "book_id", "vector", "book__name"
    ):
        try:
            vector = normalized_vector(embedding.vector)
        except ValueError:
            continue
        seeds.append(embedding.book_id)
        title = embedding.book.name.strip() or "Книга без назви"
        signals.append(
            _Signal(
                vector,
                weights[embedding.book_id],
                BOOK_REASONS[actions[embedding.book_id]].format(title=title),
            )
        )
        for i, value in enumerate(vector):
            total[i] += weights[embedding.book_id] * value
    if queries:
        # Reuse the existing process-local model, without storing a second profile
        # or caching private query text. Model failure preserves book signals.
        try:
            model = embeddings.load_embedding_model()
        except Exception:
            model = None
        if model is not None:
            for query in queries:
                try:
                    vector = normalized_vector(
                        next(
                            iter(model.embed([spec.query_prefix + query], batch_size=1))
                        )
                    )
                except Exception:
                    continue
                signals.append(
                    _Signal(
                        vector,
                        SEARCH_WEIGHT,
                        f"Рекомендовано за вашим пошуком «{query}».",
                    )
                )
                for i, value in enumerate(vector):
                    total[i] += SEARCH_WEIGHT * value
    try:
        return normalized_vector(total), seeds, signals
    except ValueError:
        return None, seeds, signals


def recommend_books(user, limit=DEFAULT_LIMIT):
    """Return up to ``limit`` available, not-currently-held books for this account.

    A weighted centroid ranks unseen compatible books by cosine similarity. Missing
    vectors are filled from a stable alphabetical list. No additional model,
    training, cross-reader popularity, persisted profile or availability cache is needed.
    Only text-search signals need inference through the existing shared encoder.
    """
    if not is_signed_in(user):
        raise PermissionDenied("Sign in to request recommendations.")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_LIMIT
    ):
        raise ValueError(f"limit must be an integer from 1 to {MAX_LIMIT}.")
    now = timezone.now()
    books = available_candidates(user, now=now)
    profile, seeds, signals = _profile(user, now)
    results = []
    if profile is not None:
        spec = resolve()
        books = books.exclude(pk__in=seeds)
        results = list(
            books.filter(
                embedding__model=spec.repository, embedding__model_revision=spec.tag
            )
            .select_related("embedding")
            .alias(distance=CosineDistance("embedding__vector", profile))
            .order_by("distance", "id")[:limit]
        )
    for book in results:
        book.reason = _reason(book, signals)
    if len(results) < limit:
        fallback = list(
            fallback_candidates(
                user,
                now=now,
                exclude_book_ids=(seeds if profile is not None else [])
                + [book.pk for book in results],
            )[: limit - len(results)]
        )
        for book in fallback:
            book.reason = FALLBACK_REASON
        results += fallback
    return results
