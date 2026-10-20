# ---- Django Library app container ----
FROM python:3.12-slim

# Disable Python bytecode writing (smaller image, no stale .pyc)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=library.settings \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt && \
    rm -rf /root/.cache

# Embedding model setting. Empty values mean the defaults in
# library/book/embedding_config.py; pass --build-arg to choose another model.
# The values also reach the runtime environment, so the app's startup check can
# tell when a runtime override differs from the model baked into this image.
ARG BOOK_EMBEDDING_MODEL \
    BOOK_EMBEDDING_MODEL_REVISION \
    BOOK_EMBEDDING_MODEL_FILE \
    BOOK_EMBEDDING_TOKENIZER_FILE \
    BOOK_EMBEDDING_DIMENSIONS \
    BOOK_EMBEDDING_POOLING \
    BOOK_EMBEDDING_QUERY_PREFIX \
    BOOK_EMBEDDING_DOCUMENT_PREFIX \
    BOOK_EMBEDDING_MAX_TOKENS
ENV BOOK_EMBEDDING_MODEL=${BOOK_EMBEDDING_MODEL} \
    BOOK_EMBEDDING_MODEL_REVISION=${BOOK_EMBEDDING_MODEL_REVISION} \
    BOOK_EMBEDDING_MODEL_FILE=${BOOK_EMBEDDING_MODEL_FILE} \
    BOOK_EMBEDDING_TOKENIZER_FILE=${BOOK_EMBEDDING_TOKENIZER_FILE} \
    BOOK_EMBEDDING_DIMENSIONS=${BOOK_EMBEDDING_DIMENSIONS} \
    BOOK_EMBEDDING_POOLING=${BOOK_EMBEDDING_POOLING} \
    BOOK_EMBEDDING_QUERY_PREFIX=${BOOK_EMBEDDING_QUERY_PREFIX} \
    BOOK_EMBEDDING_DOCUMENT_PREFIX=${BOOK_EMBEDDING_DOCUMENT_PREFIX} \
    BOOK_EMBEDDING_MAX_TOKENS=${BOOK_EMBEDDING_MAX_TOKENS} \
    BOOK_EMBEDDING_CACHE_DIR=/app/.cache/book-embeddings \
    HF_HUB_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false

# Bake the configured model into the image: containers never download one.
COPY library/book/embedding_config.py /app/library/book/embedding_config.py
COPY scripts/fetch_embedding_model.py /app/scripts/fetch_embedding_model.py
RUN HF_HUB_OFFLINE=0 python /app/scripts/fetch_embedding_model.py --cache-dir /app/.cache/book-embeddings

# Copy source after dependencies/model so code changes reuse build layers.
COPY . /app
WORKDIR /app/library

# Collect static files (Django admin CSS/JS) so WhiteNoise can serve them
# even when DEBUG=False. Uses STATIC_ROOT = library/staticfiles.
# Settings require a key; scoping it to this command keeps it out of the image
# environment, so a container without a real SECRET_KEY refuses to start.
RUN SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput --clear

# Bash-like entrypoint (sh is fine on slim)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

# The commit this image was built from (CI passes github.sha), reported by
# /api/v1/version/. Last, so a new commit reuses every cached layer above.
ARG APP_COMMIT=unknown
ENV APP_COMMIT=${APP_COMMIT}

ENTRYPOINT ["/entrypoint.sh"]
# Production server: gunicorn, configured by library/gunicorn.conf.py (workers
# from WEB_CONCURRENCY, each warmed up with the model).
CMD ["gunicorn", "library.wsgi:application", "--bind", "0.0.0.0:8000"]
