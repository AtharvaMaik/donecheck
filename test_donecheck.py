import tempfile
import unittest
from pathlib import Path
from unittest import mock

import donecheck


class DoneCheckTests(unittest.TestCase):
    def test_scans_unfinished_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.py"
            marker = "TO" + "DO"
            path.write_text(f"def ship():\n    # {marker} before launch\n    return True\n", encoding="utf-8")

            findings = donecheck.scan_file(path)

        self.assertEqual(findings[0].rule, "unfinished_marker")
        self.assertEqual(findings[0].line, 2)

    def test_markdown_code_fences_are_examples_not_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            marker = "TO" + "DO"
            path.write_text(f"```python\n# {marker} example\n```\nShip it.\n", encoding="utf-8")

            findings = donecheck.scan_file(path)

        self.assertEqual(findings, [])

    def test_missing_files_and_commands_fails(self):
        result = donecheck.assess([], [])

        self.assertEqual(result, "FAIL")

    def test_base_ref_scans_merge_base_diff(self):
        with mock.patch("donecheck.git_output", return_value="app.py\nREADME.md\n") as git_output:
            files = donecheck.changed_files("origin/main")

        git_output.assert_called_once_with(["diff", "--name-only", "origin/main..HEAD"])
        self.assertEqual(files, [Path("app.py"), Path("README.md")])


if __name__ == "__main__":
    unittest.main()
