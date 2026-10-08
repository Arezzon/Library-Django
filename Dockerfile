# ---- Django Library app container ----
FROM python:3.12-slim

# Disable Python bytecode writing (smaller image, no stale .pyc)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=library.settings \
    PIP_NO_CACHE_DIR=1 \
    # Build-time fallback so collectstatic has a key to read during image build.
    # Overridden at runtime by the real SECRET_KEY from the environment.
    SECRET_KEY=build-time-placeholder-not-used-at-runtime

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt && \
    rm -rf /root/.cache

# Bake the pinned int8 model into the image: no cold-start model download.
ENV BOOK_EMBEDDING_CACHE_DIR=/app/.cache/book-embeddings \
    HF_HUB_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false
RUN HF_HUB_OFFLINE=0 python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='intfloat/multilingual-e5-small', revision='614241f622f53c4eeff9890bdc4f31cfecc418b3', cache_dir='/app/.cache/book-embeddings', allow_patterns=['onnx/sentencepiece.bpe.model', 'onnx/model_qint8_avx512_vnni.onnx'])"

# Copy source after dependencies/model so code changes reuse build layers.
COPY . /app
WORKDIR /app/library

# Collect static files (Django admin CSS/JS) so WhiteNoise can serve them
# even when DEBUG=False. Uses STATIC_ROOT = library/staticfiles.
RUN python manage.py collectstatic --noinput --clear

# Bash-like entrypoint (sh is fine on slim)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
# Production server: gunicorn. The entrypoint binds to $PORT (default 8000),
# so Render's injected PORT is honored automatically.
CMD ["gunicorn", "library.wsgi:application", "--workers", "3", "--timeout", "60"]
