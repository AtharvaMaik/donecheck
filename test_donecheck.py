import io
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

    def test_changed_code_path_needs_command_evidence(self):
        commands = [donecheck.CommandResult("python -m py_compile other.py", 0, "")]

        findings = donecheck.proof_findings([], commands, [Path("app.py")])

        self.assertEqual(findings[0].rule, "missing_path_evidence")
        self.assertIn("app.py", findings[0].text)

    def test_no_verification_command_is_skipped_for_changed_files(self):
        result = donecheck.assess([], [], [Path("app.py")])

        self.assertEqual(result, "SKIPPED")

    def test_thin_proof_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            proof = Path(tmp) / "PROOF.md"
            proof.write_text("# Proof\n\nTests passed.\n", encoding="utf-8")

            findings = donecheck.proof_file_findings([proof], "fresh")

        self.assertEqual(findings[0].rule, "thin_proof_file")

    def test_stale_donecheck_receipt_is_flagged_when_hash_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            proof = Path(tmp) / "PROOF.md"
            proof.write_text("# DoneCheck Receipt: PASS\n\n- evidence hash: `old`\n", encoding="utf-8")

            findings = donecheck.proof_file_findings([proof], "fresh")

        self.assertEqual(findings[0].rule, "stale_proof")

    def test_source_files_are_not_proof_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "donecheck.py"
            source.write_text('# DoneCheck Receipt: PASS\n', encoding="utf-8")

            findings = donecheck.proof_file_findings([source], "fresh")

        self.assertEqual(findings, [])

    def test_receipt_records_stale_inputs(self):
        body = donecheck.receipt(
            [],
            [donecheck.CommandResult("pytest -q", 0, "ok")],
            [Path("app.py")],
            0.1,
            evidence_hash="abc123",
            base_ref="origin/main",
            base_commit="base123",
        )

        self.assertIn("- base: `origin/main`", body)
        self.assertIn("- base commit: `base123`", body)
        self.assertIn("- evidence hash: `abc123`", body)
        self.assertIn("stale if", body)

    def test_base_ref_scans_merge_base_diff(self):
        def git_output(args):
            if args == ["merge-base", "origin/main", "HEAD"]:
                return "abc123"
            if args == ["diff", "--name-only", "abc123..HEAD"]:
                return "app.py\nREADME.md\n"
            self.fail(f"unexpected git args: {args}")

        with mock.patch("donecheck.git_output", side_effect=git_output) as mocked_git_output:
            files = donecheck.changed_files("origin/main")

        mocked_git_output.assert_has_calls(
            [
                mock.call(["merge-base", "origin/main", "HEAD"]),
                mock.call(["diff", "--name-only", "abc123..HEAD"]),
            ]
        )
        self.assertEqual(files, [Path("app.py"), Path("README.md")])

    def test_action_inputs_are_not_raw_shell_interpolation(self):
        text = Path("action.yml").read_text(encoding="utf-8")

        self.assertIn("DONECHECK_COMMAND: ${{ inputs.command }}", text)
        self.assertIn('donecheck+=(--cmd "$DONECHECK_COMMAND")', text)
        self.assertIn('shlex.split(os.environ["DONECHECK_ARGS"])', text)
        self.assertNotIn('donecheck+=(--cmd "${{ inputs.command }}")', text)
        self.assertNotIn("donecheck+=(${{ inputs.args }})", text)

    def test_summary_lists_findings_and_commands(self):
        findings = [donecheck.Finding("missing_evidence", "-", 0, "no files or commands checked")]
        commands = [donecheck.CommandResult("pytest -q", 1, "boom stacktrace")]

        text = donecheck.summary("FAIL", findings, commands)

        self.assertIn("DoneCheck: FAIL", text)
        self.assertIn("missing_evidence -:0 no files or commands checked", text)
        self.assertIn("command failed: pytest -q", text)
        self.assertIn("boom stacktrace", text)

    def test_github_step_summary_gets_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "DONECHECK.md"
            step_summary = Path(tmp) / "summary.md"
            with mock.patch("donecheck.git_output", return_value=""):
                with mock.patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(step_summary)}):
                    with mock.patch("sys.stdout", io.StringIO()):
                        code = donecheck.main(["--write", str(receipt)])

            self.assertEqual(code, 1)
            self.assertTrue(step_summary.exists(), "expected GitHub step summary file")
            self.assertIn("# DoneCheck Receipt: FAIL", step_summary.read_text(encoding="utf-8"))

    def test_github_step_summary_write_errors_are_visible(self):
        stderr = io.StringIO()
        with mock.patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": "bad/path"}):
            with mock.patch("pathlib.Path.open", side_effect=OSError("nope")):
                with mock.patch("sys.stderr", stderr):
                    donecheck.write_github_step_summary("body")

        self.assertIn("could not write GitHub step summary", stderr.getvalue())

    def test_init_action_writes_github_action_workflow(self):
        init_action = getattr(donecheck, "init_action", None)
        self.assertIsNotNone(init_action, "--init should expose init_action")
        if init_action is None:
            return

        with tempfile.TemporaryDirectory() as tmp:
            workflow = Path(tmp) / ".github" / "workflows" / "donecheck.yml"
            with mock.patch("sys.stdout", io.StringIO()):
                code = init_action("pytest -q", workflow)

            text = workflow.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("uses: AtharvaMaik/donecheck@v0.1.8", text)
        self.assertIn("command: >-", text)
        self.assertIn("pytest -q", text)

    def test_github_annotations_escape_special_characters(self):
        finding = donecheck.Finding("unfinished_marker", "app.py", 2, "bad: line\nnext")

        lines = donecheck.github_annotations([finding])

        self.assertEqual(lines, ["::error file=app.py,line=2,title=unfinished_marker::bad: line%0Anext"])

    def test_version_flag_prints_version(self):
        stdout = io.StringIO()

        with mock.patch("sys.stdout", stdout):
            with self.assertRaises(SystemExit) as raised:
                donecheck.main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("donecheck 0.1.8", stdout.getvalue())

    def test_agent_prompt_prints_copy_paste_instruction(self):
        stdout = io.StringIO()

        with mock.patch("sys.stdout", stdout):
            code = donecheck.main(["--agent-prompt", "--cmd", "pytest -q"])

        self.assertEqual(code, 0)
        self.assertIn('donecheck --cmd "pytest -q"', stdout.getvalue())
        self.assertIn("Before claiming done", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
