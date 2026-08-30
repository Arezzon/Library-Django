# ---- Django Library app container ----
FROM python:3.12-slim

# Disable Python bytecode writing (smaller image, no stale .pyc)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=library.settings \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy the whole repo, then move into the Django project directory
COPY . /app
WORKDIR /app/library

RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt && \
    rm -rf /root/.cache

# Bash-like entrypoint (sh is fine on slim)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
