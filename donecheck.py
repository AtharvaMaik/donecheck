"""DoneCheck: make coding agents prove "done" with local evidence."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_EXCLUDES = (
    ".git/*",
    ".venv/*",
    "venv/*",
    "node_modules/*",
    "dist/*",
    "build/*",
    "__pycache__/*",
    "*.lock",
    "*.md",
    "DONECHECK.md",
)

UNFINISHED_WORDS = ("TO" + "DO", "FIX" + "ME", "X" * 3, "HA" + "CK")
UNFINISHED_PHRASES = ("not " + "implemented", "coming " + "soon", "st" + "ub")
UNFINISHED_RE = r"\b(" + "|".join(UNFINISHED_WORDS) + r")\b|" + "|".join(re.escape(p) for p in UNFINISHED_PHRASES)

RULES = (
    ("unfinished_marker", re.compile(UNFINISHED_RE, re.I)),
    ("python_silent_failure", re.compile(r"except\b[^\n:]*:\s*(?:\n\s*)?(pass|return None)\b", re.I)),
    ("js_silent_failure", re.compile(r"catch\s*\([^)]*\)\s*{\s*(?:/\*.*?\*/\s*)?}", re.I | re.S)),
    ("unsafe_eval", re.compile(r"\b(eval|exec)\s*\(", re.I)),
    ("secret_literal", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\n]{8,}['\"]")),
)


@dataclasses.dataclass
class Finding:
    rule: str
    path: str
    line: int
    text: str


@dataclasses.dataclass
class CommandResult:
    command: str
    code: int
    output: str


def run(command: str) -> CommandResult:
    proc = subprocess.run(command, shell=True, text=True, capture_output=True)
    output = (proc.stdout + proc.stderr).strip()
    return CommandResult(command, proc.returncode, output)


def git_output(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], text=True, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or "not a git repository")
    return proc.stdout.strip()


def current_commit() -> str:
    proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], text=True, capture_output=True)
    return proc.stdout.strip() if proc.returncode == 0 else "no-commit-yet"


def changed_files() -> list[Path]:
    names = set()
    for args in (["diff", "--name-only"], ["diff", "--cached", "--name-only"], ["ls-files", "--others", "--exclude-standard"]):
        names.update(line for line in git_output(args).splitlines() if line)
    return [Path(name) for name in sorted(names)]


def excluded(path: Path, patterns: tuple[str, ...]) -> bool:
    value = path.as_posix()
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


def scan_file(path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    findings: list[Finding] = []
    lines = text.splitlines()
    for rule, pattern in RULES:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            snippet = lines[line - 1].strip() if line <= len(lines) else match.group(0).strip()
            findings.append(Finding(rule, path.as_posix(), line, snippet[:160]))
    return findings


def scan(paths: list[Path], excludes: tuple[str, ...]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if path.is_file() and not excluded(path, excludes):
            findings.extend(scan_file(path))
    return findings


def receipt(
    findings: list[Finding],
    commands: list[CommandResult],
    files: list[Path],
    elapsed: float,
) -> str:
    sha = current_commit() if Path(".git").exists() else "no-git"
    status = "PASS" if not findings and all(c.code == 0 for c in commands) else "FAIL"
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        f"# DoneCheck Receipt: {status}",
        "",
        f"- commit: `{sha}`",
        f"- generated: `{now}`",
        f"- files checked: `{len(files)}`",
        f"- findings: `{len(findings)}`",
        f"- commands: `{len(commands)}`",
        f"- elapsed: `{elapsed:.2f}s`",
        "",
        "## Findings",
        "",
    ]
    if findings:
        lines += [f"- `{f.rule}` in `{f.path}:{f.line}`: {f.text}" for f in findings]
    else:
        lines.append("- none")

    lines += ["", "## Commands", ""]
    if commands:
        for command in commands:
            lines += [
                f"### `{command.command}`",
                "",
                f"- exit code: `{command.code}`",
                "",
                "```text",
                command.output[-4000:] or "(no output)",
                "```",
                "",
            ]
    else:
        lines.append("- none supplied")

    lines += ["", "## Files", ""]
    lines += [f"- `{path.as_posix()}`" for path in files] or ["- none"]
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Make coding agents prove done with local evidence.")
    parser.add_argument("--cmd", action="append", default=[], help="verification command to run, repeatable")
    parser.add_argument("--write", default="DONECHECK.md", help="receipt path, or '-' for stdout")
    parser.add_argument("--all", action="store_true", help="scan every tracked file instead of changed files")
    parser.add_argument("--exclude", action="append", default=[], help="extra glob to skip")
    parser.add_argument("--no-fail-on-findings", action="store_true", help="write receipt but exit 0 for findings")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    started = dt.datetime.now().timestamp()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    paths = [Path(p) for p in git_output(["ls-files"]).splitlines()] if args.all else changed_files()
    excludes = (*DEFAULT_EXCLUDES, *tuple(args.exclude))
    findings = scan(paths, excludes)
    commands = [run(command) for command in args.cmd]
    elapsed = dt.datetime.now().timestamp() - started
    body = receipt(findings, commands, paths, elapsed)

    if args.write == "-":
        print(body, end="")
    else:
        Path(args.write).write_text(body, encoding="utf-8")

    command_failed = any(command.code != 0 for command in commands)
    finding_failed = findings and not args.no_fail_on_findings
    return 1 if command_failed or finding_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
