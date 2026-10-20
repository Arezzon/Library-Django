#!/usr/bin/env python3
"""Download the configured embedding model and record it in manifest.json.

The model comes from library/book/embedding_config.py and its BOOK_EMBEDDING_*
overrides; this script names no model itself. The image build runs it, and it
also pre-fetches the model for a local virtualenv:

    python scripts/fetch_embedding_model.py [--cache-dir DIR] [--print]

Exit codes: 0 success, 2 invalid setting, 3 download failed.
"""

import argparse
import dataclasses
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "library" / "book" / "embedding_config.py"


def load_config():
    spec = importlib.util.spec_from_file_location("embedding_config", CONFIG)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cache-dir",
        default=os.getenv("BOOK_EMBEDDING_CACHE_DIR")
        or str(ROOT / ".cache" / "book-embeddings"),
        help="Model cache directory (default: $BOOK_EMBEDDING_CACHE_DIR).",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print the resolved model spec and tag as JSON; download nothing.",
    )
    args = parser.parse_args()

    try:
        model = load_config().resolve()
    except ValueError as error:
        print(f"Invalid embedding model setting: {error}", file=sys.stderr)
        return 2
    spec = dataclasses.asdict(model)
    if args.print_only:
        print(json.dumps({"spec": spec, "tag": model.tag}, indent=2))
        return 0

    cache_dir = Path(args.cache_dir)
    try:
        from huggingface_hub import snapshot_download

        snapshot = Path(
            snapshot_download(
                repo_id=model.repository,
                revision=model.revision,
                cache_dir=str(cache_dir),
                allow_patterns=[model.model_file, model.tokenizer_file],
            )
        )
        missing = [
            name
            for name in (model.model_file, model.tokenizer_file)
            if not (snapshot / name).is_file()
        ]
        if missing:
            raise FileNotFoundError(f"not in the repository: {', '.join(missing)}")
    except Exception as error:
        print(
            f"Could not download {model.repository}@{model.revision}: {error}",
            file=sys.stderr,
        )
        return 3

    manifest = {"spec": spec, "tag": model.tag, "snapshot_path": str(snapshot)}
    path = cache_dir / "manifest.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"Fetched {model.repository}@{model.revision} (tag {model.tag}) to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
