"""Gunicorn settings, loaded automatically from the working directory (/app/library).

The entrypoint adds --bind for $PORT. Each worker holds its own copy of the
embedding model (about 0.6 GB), so WEB_CONCURRENCY is the main memory knob.
"""

import os

from library.logs import build_logging_config

workers = int(os.getenv("WEB_CONCURRENCY", "3"))
timeout = 60

# The same line format as Django's logging (library/logs.py). The access log stays
# off, because URLs can carry search text.
logconfig_dict = build_logging_config("web", os.getenv("LOG_LEVEL", "INFO"))
loglevel = os.getenv("LOG_LEVEL", "INFO").lower()
accesslog = None


def post_worker_init(worker):
    """Load the model before the worker takes requests, not on the first search."""
    from book.embeddings import load_embedding_model

    load_embedding_model()
