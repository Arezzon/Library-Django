"""The single embedding model setting, its tag, the image manifest and its checks.

The default model's identity is asserted by shape only: the model may be named in
embedding_config.py alone (FR-030), so these tests never repeat it.
"""

import dataclasses
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core import checks
from django.test import SimpleTestCase, override_settings

from .embedding_config import EmbeddingSpec, read_manifest, resolve, threads

VARIABLES = {
    "BOOK_EMBEDDING_MODEL": ("repository", "owner/other-model", "owner/other-model"),
    "BOOK_EMBEDDING_MODEL_REVISION": ("revision", "a" * 40, "a" * 40),
    "BOOK_EMBEDDING_MODEL_FILE": ("model_file", "onnx/model.onnx", "onnx/model.onnx"),
    "BOOK_EMBEDDING_TOKENIZER_FILE": ("tokenizer_file", "tok.model", "tok.model"),
    "BOOK_EMBEDDING_DIMENSIONS": ("dimensions", "768", 768),
    "BOOK_EMBEDDING_POOLING": ("pooling", "mean", "mean"),
    "BOOK_EMBEDDING_QUERY_PREFIX": ("query_prefix", "query: ", "query: "),
    "BOOK_EMBEDDING_DOCUMENT_PREFIX": ("document_prefix", "passage: ", "passage: "),
    "BOOK_EMBEDDING_MAX_TOKENS": ("max_tokens", "256", 256),
}


def environment(**values):
    """Patch os.environ with no BOOK_EMBEDDING_* variables except the given ones."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("BOOK_EMBEDDING_")}
    env.update(values)
    return patch.dict(os.environ, env, clear=True)


class EmbeddingSpecTests(SimpleTestCase):
    def test_defaults(self):
        with environment():
            spec = resolve()
        self.assertRegex(spec.repository, r"^[\w.-]+/[\w.-]+$")
        self.assertRegex(spec.revision, r"^[0-9a-f]{40}$")
        self.assertTrue(spec.model_file.endswith(".onnx"))
        self.assertIsNone(re.search(r"avx2|avx512|vnni", spec.model_file))
        self.assertEqual(spec.tokenizer_file, "sentencepiece.bpe.model")
        self.assertEqual(spec.dimensions, 1024)
        self.assertEqual(spec.pooling, "cls")
        self.assertEqual(spec.query_prefix, "")
        self.assertEqual(spec.document_prefix, "")
        self.assertEqual(spec.max_tokens, 512)

    def test_each_override_applies_and_empty_means_default(self):
        with environment():
            default = resolve()
        for variable, (field, raw, parsed) in VARIABLES.items():
            with self.subTest(variable=variable):
                with environment(**{variable: raw}):
                    self.assertEqual(getattr(resolve(), field), parsed)
                with environment(**{variable: ""}):
                    self.assertEqual(resolve(), default)

    def test_invalid_values_name_the_variable(self):
        cases = [
            ("BOOK_EMBEDDING_MODEL", "no-owner"),
            ("BOOK_EMBEDDING_MODEL_REVISION", "main"),
            ("BOOK_EMBEDDING_MODEL_REVISION", "A" * 39),
            ("BOOK_EMBEDDING_POOLING", "max"),
            ("BOOK_EMBEDDING_DIMENSIONS", "0"),
            ("BOOK_EMBEDDING_DIMENSIONS", "-3"),
            ("BOOK_EMBEDDING_DIMENSIONS", "many"),
            ("BOOK_EMBEDDING_MAX_TOKENS", "7"),
            ("BOOK_EMBEDDING_MAX_TOKENS", "8193"),
            ("BOOK_EMBEDDING_MODEL_FILE", "onnx/model_avx2.onnx"),
            ("BOOK_EMBEDDING_MODEL_FILE", "onnx/model_qint8_avx512.onnx"),
            ("BOOK_EMBEDDING_MODEL_FILE", "onnx/model_vnni.onnx"),
        ]
        for variable, value in cases:
            with self.subTest(variable=variable, value=value):
                with environment(**{variable: value}):
                    with self.assertRaisesRegex(ValueError, variable):
                        resolve()

    def test_boundary_token_limits_are_accepted(self):
        for value in ("8", "8192"):
            with environment(BOOK_EMBEDDING_MAX_TOKENS=value):
                self.assertEqual(resolve().max_tokens, int(value))

    def test_resolve_reads_the_environment_on_every_call(self):
        with environment(BOOK_EMBEDDING_DIMENSIONS="8"):
            self.assertEqual(resolve().dimensions, 8)
        with environment(BOOK_EMBEDDING_DIMENSIONS="16"):
            self.assertEqual(resolve().dimensions, 16)

    def test_spec_is_frozen(self):
        with environment():
            spec = resolve()
        self.assertIsInstance(spec, EmbeddingSpec)
        with self.assertRaises(AttributeError):
            spec.dimensions = 3


class EmbeddingTagTests(SimpleTestCase):
    def test_tag_is_a_sha1_of_the_whole_spec(self):
        with environment():
            tag = resolve().tag
        self.assertRegex(tag, r"^[0-9a-f]{40}$")
        for variable, (_field, raw, _parsed) in VARIABLES.items():
            with self.subTest(variable=variable), environment(**{variable: raw}):
                self.assertNotEqual(resolve().tag, tag)

    def test_threads_do_not_change_the_tag(self):
        with environment():
            tag = resolve().tag
        with environment(BOOK_EMBEDDING_THREADS="4"):
            self.assertEqual(resolve().tag, tag)

    def test_threads_default_minimum_and_validation(self):
        with environment():
            self.assertEqual(threads(), 2)
        with environment(BOOK_EMBEDDING_THREADS=""):
            self.assertEqual(threads(), 2)
        with environment(BOOK_EMBEDDING_THREADS="4"):
            self.assertEqual(threads(), 4)
        with environment(BOOK_EMBEDDING_THREADS="0"):
            self.assertEqual(threads(), 1)
        with environment(BOOK_EMBEDDING_THREADS="few"):
            with self.assertRaisesRegex(ValueError, "BOOK_EMBEDDING_THREADS"):
                threads()


class ManifestTests(SimpleTestCase):
    def test_missing_manifest_is_none_and_present_manifest_is_parsed(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(read_manifest(directory))
            content = {"spec": {"dimensions": 4}, "tag": "t", "snapshot_path": "/x"}
            (Path(directory) / "manifest.json").write_text(json.dumps(content))
            self.assertEqual(read_manifest(Path(directory)), content)


class EmbeddingModelCheckTests(SimpleTestCase):
    def run_book_checks(self, directory):
        with override_settings(BOOK_EMBEDDING_CACHE_DIR=Path(directory)):
            return [m for m in checks.run_checks() if m.id.startswith("book.")]

    def write_manifest(self, directory, spec):
        manifest = {
            "spec": dataclasses.asdict(spec),
            "tag": spec.tag,
            "snapshot_path": str(directory),
        }
        (Path(directory) / "manifest.json").write_text(json.dumps(manifest))

    def test_matching_manifest_reports_nothing(self):
        with tempfile.TemporaryDirectory() as directory, environment():
            self.write_manifest(directory, resolve())
            self.assertEqual(self.run_book_checks(directory), [])

    def test_different_image_model_is_an_error_naming_both(self):
        with tempfile.TemporaryDirectory() as directory, environment():
            with environment(BOOK_EMBEDDING_MODEL_REVISION="b" * 40):
                image = resolve()
            self.write_manifest(directory, image)
            messages = self.run_book_checks(directory)
            current = resolve()
        self.assertEqual([m.id for m in messages], ["book.E001"])
        self.assertIsInstance(messages[0], checks.Error)
        self.assertIn(f"{current.repository}@{current.revision}", messages[0].msg)
        self.assertIn(f"{image.repository}@{'b' * 40}", messages[0].msg)

    def test_missing_manifest_is_a_warning_naming_the_fetch_script(self):
        with tempfile.TemporaryDirectory() as directory, environment():
            messages = self.run_book_checks(directory)
        self.assertEqual([m.id for m in messages], ["book.W001"])
        self.assertIsInstance(messages[0], checks.Warning)
        self.assertIn(str(directory), messages[0].msg)
        self.assertIn("python scripts/fetch_embedding_model.py", messages[0].msg)


class FetchScriptTests(SimpleTestCase):
    """scripts/fetch_embedding_model.py reads the same setting (FR-031)."""

    script = settings.BASE_DIR.parent / "scripts" / "fetch_embedding_model.py"

    def run_script(self, *args, **env):
        environment = {
            k: v for k, v in os.environ.items() if not k.startswith("BOOK_EMBEDDING_")
        }
        environment.update(env)
        return subprocess.run(
            [sys.executable, str(self.script), *args],
            env=environment,
            capture_output=True,
            text=True,
        )

    def test_print_outputs_the_resolved_spec_and_tag_without_downloading(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_script("--print", "--cache-dir", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(os.listdir(directory), [])
        with environment():
            spec = resolve()
        self.assertEqual(
            json.loads(result.stdout),
            {"spec": dataclasses.asdict(spec), "tag": spec.tag},
        )

    def test_print_follows_overrides(self):
        result = self.run_script("--print", BOOK_EMBEDDING_DIMENSIONS="8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["spec"]["dimensions"], 8)

    def test_invalid_setting_exits_2_naming_the_variable(self):
        result = self.run_script("--print", BOOK_EMBEDDING_POOLING="max")
        self.assertEqual(result.returncode, 2)
        self.assertIn("BOOK_EMBEDDING_POOLING", result.stderr)
