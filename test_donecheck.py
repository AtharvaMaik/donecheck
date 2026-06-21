import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
