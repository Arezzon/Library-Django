from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from book.embedding_config import resolve, threads
from book.embeddings import (
    document_text,
    input_hash,
    load_embedding_model,
    normalized_vector,
)
from book.models import Book, BookEmbedding


class Command(BaseCommand):
    help = (
        "Generate book embeddings with the configured model and store them in pgvector."
    )

    def add_arguments(self, parser):
        parser.add_argument("--book-id", type=int, action="append", dest="book_ids")
        parser.add_argument("--batch-size", type=int, default=1)
        parser.add_argument(
            "--force", action="store_true", help="Regenerate unchanged embeddings."
        )
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Accepted for compatibility; the model always loads from the image.",
        )
        parser.add_argument(
            "--threads",
            type=int,
            default=None,
            help="ONNX Runtime threads (default: BOOK_EMBEDDING_THREADS, or 2).",
        )
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        database = options["database"]
        if database not in connections:
            raise CommandError(f"Unknown database alias: {database}")
        if connections[database].vendor != "postgresql":
            raise CommandError(
                "Book embeddings require PostgreSQL with the vector extension."
            )
        if options["batch_size"] <= 0:
            raise CommandError("--batch-size must be positive.")
        if options["threads"] is None:
            options["threads"] = threads()
        if options["threads"] <= 0:
            raise CommandError("--threads must be positive.")
        spec = resolve()
        books = Book.objects.using(database).order_by("pk")
        if options["book_ids"] is not None:
            missing = set(options["book_ids"]) - set(
                books.filter(pk__in=options["book_ids"]).values_list("pk", flat=True)
            )
            if missing:
                raise CommandError(f"Unknown book IDs: {sorted(missing)}")
            books = books.filter(pk__in=options["book_ids"])
        books = books.select_related("embedding").only(
            "id",
            "name",
            "description",
            "embedding__book_id",
            "embedding__input_hash",
            "embedding__model",
            "embedding__model_revision",
        )
        model = None
        pending = []
        generated = skipped = changed = 0

        def process_batch(batch):
            nonlocal model, generated, changed
            if model is None:
                try:
                    model = load_embedding_model(
                        offline=options["offline"], threads=options["threads"]
                    )
                except Exception as error:
                    raise CommandError(
                        f"Cannot load embedding model: {error}"
                    ) from error
            try:
                vectors = [
                    normalized_vector(vector)
                    for vector in model.embed(
                        [text for _, text, _ in batch],
                        batch_size=options["batch_size"],
                    )
                ]
                if len(vectors) != len(batch):
                    raise ValueError(
                        "Model returned an unexpected number of embeddings."
                    )
            except Exception as error:
                raise CommandError(f"Embedding generation failed: {error}") from error
            for (snapshot, _text, digest), vector in zip(batch, vectors, strict=True):
                # Inference runs outside transactions. Lock briefly to avoid
                # saving a vector for a description edited during inference.
                with transaction.atomic(using=database):
                    current = (
                        Book.objects.using(database)
                        .select_for_update()
                        .filter(pk=snapshot.pk)
                        .first()
                    )
                    if (
                        current is None
                        or input_hash(document_text(current.name, current.description))
                        != digest
                    ):
                        changed += 1
                        continue
                    BookEmbedding.objects.using(database).update_or_create(
                        book=current,
                        defaults={
                            "vector": vector,
                            "input_hash": digest,
                            "model": spec.repository,
                            "model_revision": spec.tag,
                        },
                    )
                    generated += 1

        for book in books.iterator(chunk_size=options["batch_size"]):
            text = document_text(book.name, book.description)
            digest = input_hash(text)
            existing = getattr(book, "embedding", None)
            if (
                not options["force"]
                and existing is not None
                and (
                    existing.input_hash == digest
                    and existing.model == spec.repository
                    and existing.model_revision == spec.tag
                )
            ):
                skipped += 1
                continue
            pending.append((book, text, digest))
            if len(pending) == options["batch_size"]:
                process_batch(pending)
                pending = []
        if pending:
            process_batch(pending)
        self.stdout.write(
            self.style.SUCCESS(
                f"Generated: {generated}; unchanged: {skipped}; "
                f"changed during inference: {changed}."
            )
        )
        if changed:
            self.stderr.write(
                "Some books changed during inference; rerun the command to process them."
            )
