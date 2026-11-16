import json
import tempfile
import unittest
from pathlib import Path

from synthetic_apps.config import RunConfig
from synthetic_apps.local_model import LocalModelClient
from synthetic_apps.ingestion.discover import discover_dossiers
from synthetic_apps.paths import ensure_safe_output
from synthetic_apps.schemas import FeatureValue


class ContractTests(unittest.TestCase):
    def test_default_count_is_five(self):
        self.assertEqual(RunConfig().count, 5)

    def test_unknown_is_not_false(self):
        feature = FeatureValue()
        self.assertIsNone(feature.value)
        self.assertEqual(feature.status, "unknown")

    def test_discovery_uses_relative_dossier_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "A").mkdir()
            (root / "A" / "CV.pdf").write_bytes(b"fixture")
            found = discover_dossiers(root)
            self.assertEqual(found[0].relative_path, "A")
            self.assertEqual(found[0].files[0].name, "CV.pdf")

    def test_output_cannot_be_inside_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                ensure_safe_output(root / "out", root)

    def test_private_track_requires_private_cache(self):
        with self.assertRaises(ValueError):
            RunConfig(track="private").validate(require_input=False)

    def test_local_model_rejects_non_loopback(self):
        with self.assertRaises(ValueError):
            LocalModelClient("https://example.invalid/v1")


if __name__ == "__main__":
    unittest.main()
