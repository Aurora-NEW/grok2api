from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ghcr-image.yml"


class GHCRWorkflowTests(unittest.TestCase):
    def test_tag_builds_disable_automatic_latest_tags(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        build_section = self._job_section(source, "build_ghcr_image", "merge")
        merge_section = self._job_section(source, "merge")
        for job_name, section in (("build_ghcr_image", build_section), ("merge", merge_section)):
            metadata = re.search(r"uses: docker/metadata-action@v5(?P<body>.*?)(?:\n\s+- name:|\Z)", section, re.DOTALL)
            self.assertIsNotNone(metadata, f"{job_name} metadata step is missing")
            metadata_body = metadata.group("body")
            self.assertIn("flavor: latest=false", metadata_body, f"{job_name} must disable metadata-action's automatic latest tag")
            self.assertIn("type=raw,value=latest", metadata_body, f"{job_name} must retain the explicit main-branch latest tag")

    def test_workflow_runs_this_regression_test(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest scripts/test_ghcr_workflow.py", source)

    def _job_section(self, source: str, start: str, end: str | None = None) -> str:
        start_marker = f"  {start}:\n"
        start_index = source.index(start_marker)
        if end is None:
            return source[start_index:]
        end_marker = f"  {end}:\n"
        return source[start_index:source.index(end_marker, start_index + len(start_marker))]


if __name__ == "__main__":
    unittest.main()
