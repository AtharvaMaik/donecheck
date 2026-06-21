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

    def test_summary_lists_findings_and_commands(self):
        findings = [donecheck.Finding("missing_evidence", "-", 0, "no files or commands checked")]
        commands = [donecheck.CommandResult("pytest -q", 1, "failed")]

        text = donecheck.summary("FAIL", findings, commands)

        self.assertIn("DoneCheck: FAIL", text)
        self.assertIn("missing_evidence -:0 no files or commands checked", text)
        self.assertIn("command failed: pytest -q", text)

    def test_github_annotations_escape_special_characters(self):
        finding = donecheck.Finding("unfinished_marker", "app.py", 2, "bad: line\nnext")

        lines = donecheck.github_annotations([finding])

        self.assertEqual(lines, ["::error file=app.py,line=2,title=unfinished_marker::bad: line%0Anext"])


if __name__ == "__main__":
    unittest.main()
