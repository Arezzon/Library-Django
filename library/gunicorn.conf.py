"""Gunicorn settings, loaded automatically from the working directory (/app/library).

The entrypoint adds --bind for $PORT. Each worker holds its own copy of the
embedding model (about 0.6 GB), so WEB_CONCURRENCY is the main memory knob.
"""

import os

workers = int(os.getenv("WEB_CONCURRENCY", "3"))
timeout = 60


def post_worker_init(worker):
    """Load the model before the worker takes requests, not on the first search."""
    from book.embeddings import load_embedding_model

    load_embedding_model()
