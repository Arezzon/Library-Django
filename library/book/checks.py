"""Startup checks: the runtime model setting must match the model in the image.

``migrate`` runs these, and the entrypoint runs ``migrate`` first, so a
mismatched override stops the web container before it serves traffic.
"""

from django.conf import settings
from django.core import checks

from .embedding_config import read_manifest, resolve


@checks.register()
def check_embedding_model(app_configs=None, **kwargs):
    cache_dir = settings.BOOK_EMBEDDING_CACHE_DIR
    manifest = read_manifest(cache_dir)
    if manifest is None:
        return [
            checks.Warning(
                f"No embedding model found in {cache_dir}; "
                "run python scripts/fetch_embedding_model.py.",
                id="book.W001",
            )
        ]
    spec = resolve()
    if manifest.get("tag") == spec.tag:
        return []
    image = manifest.get("spec", {})
    return [
        checks.Error(
            f"Embedding model setting {spec.repository}@{spec.revision} does not "
            "match the model in this image "
            f"{image.get('repository')}@{image.get('revision')}. Rebuild the image "
            "with the new setting or remove the override.",
            id="book.E001",
        )
    ]
