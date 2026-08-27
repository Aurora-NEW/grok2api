from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts" / "verify-production-custom-release.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "ghcr-image.yml"


class ReleaseMetadataTests(unittest.TestCase):
    def test_production_verifier_uses_third_release_candidate(self) -> None:
        source = VERIFY_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("/v3.1.5-aurora.3-image-ref", source)
        self.assertIn("/pre-v3.1.5-aurora.3/account-count", source)
        self.assertNotIn("v3.1.5-aurora.2", source)
        self.assertNotIn("v3.1.5-aurora.1", source)

    def test_workflow_runs_release_metadata_test(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest scripts/test_release_metadata.py", source)


if __name__ == "__main__":
    unittest.main()
