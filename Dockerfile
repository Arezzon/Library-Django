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

# Copy the whole repo, then move into the Django project directory
COPY . /app
WORKDIR /app/library

RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt && \
    rm -rf /root/.cache

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
