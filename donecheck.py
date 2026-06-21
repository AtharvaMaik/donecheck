"""DoneCheck: make coding agents prove "done" with local evidence."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fnmatch
import hashlib
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
    "DONECHECK.md",
)

VERSION = "0.1.8"
ACTION_REF = "v0.1.8"

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
CODE_SUFFIXES = {
    ".c",
    ".cfg",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
BROAD_COMMAND_RE = re.compile(
    r"\b(pytest|unittest|tox|nox|cargo\s+test|go\s+test|dotnet\s+test|mvn\s+test|gradle\b.*\btest|npm\s+(?:run\s+)?test|pnpm\s+test|yarn\s+test)\b",
    re.I,
)
PROOF_FILE_RE = re.compile(r"(donecheck|proof|verification|test[-_]?results)", re.I)
PROOF_EXTENSIONS = {".md", ".markdown", ".txt"}
THIN_PROOF_RE = re.compile(r"\b(all\s+)?tests?\s+pass(?:ed|es)?\b", re.I)
STALE_INPUT_PATTERNS = (
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "requirements*.txt",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "go.sum",
    "Gemfile.lock",
    "migrations/*",
    "migrations/**/*",
    "db/migrations/*",
    "db/migrations/**/*",
    ".env.example",
    ".env.sample",
    "schema.sql",
    "*.schema.json",
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


def merge_base(base_ref: str) -> str:
    return git_output(["merge-base", base_ref, "HEAD"])


def changed_files(base_ref: str | None = None, base_commit: str | None = None) -> list[Path]:
    if base_ref:
        base_commit = base_commit or merge_base(base_ref)
        return [Path(line) for line in git_output(["diff", "--name-only", f"{base_commit}..HEAD"]).splitlines() if line]

    names = set()
    for args in (["diff", "--name-only"], ["diff", "--cached", "--name-only"], ["ls-files", "--others", "--exclude-standard"]):
        names.update(line for line in git_output(args).splitlines() if line)
    return [Path(name) for name in sorted(names)]


def excluded(path: Path, patterns: tuple[str, ...]) -> bool:
    value = path.as_posix()
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


def strip_markdown_fences(text: str) -> str:
    lines = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            lines.append("")
        elif fenced:
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines)


def scan_file(path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    if path.suffix.lower() in {".md", ".markdown"}:
        text = strip_markdown_fences(text)

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


def proof_like(path: Path) -> bool:
    return path.suffix.lower() in PROOF_EXTENSIONS and bool(PROOF_FILE_RE.search(path.name))


def parse_receipt_field(text: str, field: str) -> str | None:
    pattern = re.compile(rf"^-\s*{re.escape(field)}:\s*`?([^`\n]+)`?", re.I | re.M)
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def proof_file_findings(paths: list[Path], current_hash: str, base_commit: str | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if not proof_like(path) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        has_exit = re.search(r"\bexit code\b", text, re.I)
        has_output = re.search(r"\boutput\b|```", text, re.I)
        has_time = re.search(r"\bgenerated\b|\btimestamp\b|\d{4}-\d{2}-\d{2}", text, re.I)
        if THIN_PROOF_RE.search(text) and not (has_exit and has_output and has_time):
            findings.append(
                Finding(
                    "thin_proof_file",
                    path.as_posix(),
                    1,
                    "proof says tests passed without command output, exit code, and timestamp",
                )
            )
            continue

        if "# DoneCheck Receipt:" not in text:
            continue
        saved_hash = parse_receipt_field(text, "evidence hash")
        if not saved_hash:
            findings.append(Finding("stale_proof", path.as_posix(), 1, "receipt has no evidence hash; rerun verification"))
        elif saved_hash != current_hash:
            findings.append(Finding("stale_proof", path.as_posix(), 1, "evidence changed; rerun verification"))
        saved_base = parse_receipt_field(text, "base commit")
        if base_commit and saved_base and saved_base != base_commit:
            findings.append(Finding("stale_proof", path.as_posix(), 1, "base commit changed; rerun verification"))
    return findings


def stale_input_files(files: list[Path]) -> list[Path]:
    selected = {path for path in files}
    try:
        tracked = [Path(line) for line in git_output(["ls-files"]).splitlines() if line]
    except SystemExit:
        tracked = []
    for path in tracked:
        value = path.as_posix()
        if any(fnmatch.fnmatch(value, pattern) for pattern in STALE_INPUT_PATTERNS):
            selected.add(path)
    return sorted(selected, key=lambda path: path.as_posix())


def evidence_hash(files: list[Path], commands: list[CommandResult], base_commit: str | None = None) -> str:
    digest = hashlib.sha256()
    if base_commit:
        digest.update(f"base:{base_commit}\0".encode())
    for command in commands:
        digest.update(f"cmd:{command.command}\0".encode())
    for path in sorted(files, key=lambda item: item.as_posix()):
        digest.update(f"path:{path.as_posix()}\0".encode())
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def broad_command(command: str) -> bool:
    return bool(BROAD_COMMAND_RE.search(" ".join(command.split())))


def needs_command_evidence(path: Path) -> bool:
    return path.suffix.lower() in CODE_SUFFIXES and not proof_like(path)


def command_mentions_path(command: CommandResult, path: Path) -> bool:
    haystack = f"{command.command}\n{command.output}".replace("\\", "/").lower()
    value = path.as_posix().lower()
    return value in haystack or path.name.lower() in haystack


def path_evidence_findings(commands: list[CommandResult], files: list[Path]) -> list[Finding]:
    if not commands or any(broad_command(command.command) for command in commands):
        return []
    findings = []
    for path in files:
        if needs_command_evidence(path) and not any(command_mentions_path(command, path) for command in commands):
            findings.append(
                Finding(
                    "missing_path_evidence",
                    path.as_posix(),
                    0,
                    f"no verification command mentions changed path {path.as_posix()}",
                )
            )
    return findings


def receipt(
    findings: list[Finding],
    commands: list[CommandResult],
    files: list[Path],
    elapsed: float,
    *,
    evidence_hash: str = "",
    base_ref: str | None = None,
    base_commit: str | None = None,
    skip_reasons: list[str] | None = None,
    status: str | None = None,
) -> str:
    skip_reasons = skip_reasons or []
    sha = current_commit() if Path(".git").exists() else "no-git"
    status = status or assess(findings, commands, files, skip_reasons)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    base_lines = [f"- base: `{base_ref}`", f"- base commit: `{base_commit}`"] if base_ref and base_commit else []
    lines = [
        f"# DoneCheck Receipt: {status}",
        "",
        f"- commit: `{sha}`",
        f"- generated: `{now}`",
        *base_lines,
        f"- evidence hash: `{evidence_hash or 'unavailable'}`",
        "- stale if: base commit, checked files, verification commands, dependency locks, migrations, or env contracts change",
        f"- files checked: `{len(files)}`",
        f"- findings: `{len(findings)}`",
        f"- commands: `{len(commands)}`",
        f"- skipped verification: `{len(skip_reasons)}`",
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

    lines += ["", "## Skipped Verification", ""]
    if skip_reasons:
        lines += [f"- {reason}" for reason in skip_reasons]
    else:
        lines.append("- none")

    lines += ["", "## Files", ""]
    lines += [f"- `{path.as_posix()}`" for path in files] or ["- none"]
    return "\n".join(lines).rstrip() + "\n"


def proof_findings(findings: list[Finding], commands: list[CommandResult], files: list[Path]) -> list[Finding]:
    if not findings and not commands and not files:
        return [Finding("missing_evidence", "-", 0, "no files or commands checked")]
    return findings + path_evidence_findings(commands, files)


def assess(
    findings: list[Finding],
    commands: list[CommandResult],
    files: list[Path] | None = None,
    skip_reasons: list[str] | None = None,
) -> str:
    files = files or []
    skip_reasons = skip_reasons or []
    if proof_findings(findings, commands, files):
        return "FAIL"
    if any(command.code != 0 for command in commands):
        return "FAIL"
    if skip_reasons or (files and not commands):
        return "SKIPPED"
    return "PASS"


def summary(status: str, findings: list[Finding], commands: list[CommandResult], skip_reasons: list[str] | None = None) -> str:
    skip_reasons = skip_reasons or []
    lines = [f"DoneCheck: {status}"]
    lines += [f"- {f.rule} {f.path}:{f.line} {f.text}" for f in findings]
    lines += [f"- verification skipped: {reason}" for reason in skip_reasons]
    for command in commands:
        if command.code != 0:
            lines.append(f"- command failed: {command.command}")
            if command.output:
                lines.append("  output:")
                lines += [f"  {line}" for line in command.output[-1200:].splitlines()]
    return "\n".join(lines) + "\n"


def annotation_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def github_annotations(findings: list[Finding]) -> list[str]:
    return [
        f"::error file={annotation_escape(f.path)},line={f.line},title={annotation_escape(f.rule)}::{annotation_escape(f.text)}"
        for f in findings
    ]


def write_github_step_summary(body: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with Path(summary_path).open("a", encoding="utf-8") as file:
            file.write(body)
    except OSError as error:
        print(f"DoneCheck: could not write GitHub step summary: {error}", file=sys.stderr)


def action_workflow(command: str) -> str:
    lines = [
        "name: donecheck",
        "on: [pull_request]",
        "",
        "jobs:",
        "  donecheck:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v4",
        "        with:",
        "          fetch-depth: 0",
        f"      - uses: AtharvaMaik/donecheck@{ACTION_REF}",
    ]
    command = " ".join(command.splitlines()).strip()
    if command:
        lines += [
            "        with:",
            "          command: >-",
            f"            {command}",
        ]
    return "\n".join(lines) + "\n"


def init_action(command: str, workflow: Path = Path(".github/workflows/donecheck.yml")) -> int:
    if workflow.exists():
        print(f"DoneCheck: {workflow} already exists", file=sys.stderr)
        return 1
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(action_workflow(command), encoding="utf-8")
    print(f"DoneCheck: wrote {workflow}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Make coding agents prove done with local evidence.")
    parser.add_argument("--version", action="version", version=f"donecheck {VERSION}")
    parser.add_argument("--cmd", action="append", default=[], help="verification command to run, repeatable")
    parser.add_argument("--write", default="DONECHECK.md", help="receipt path, or '-' for stdout")
    parser.add_argument("--all", action="store_true", help="scan every tracked file instead of changed files")
    parser.add_argument("--base", help="scan files changed since this git ref, for example origin/main")
    parser.add_argument("--exclude", action="append", default=[], help="extra glob to skip")
    parser.add_argument("--init", action="store_true", help="create .github/workflows/donecheck.yml")
    parser.add_argument("--agent-prompt", action="store_true", help="print a copy-paste instruction for coding agents")
    parser.add_argument("--skip-reason", action="append", default=[], help="record why verification could not run; exits non-zero")
    parser.add_argument("--no-fail-on-findings", action="store_true", help="write receipt but exit 0 for findings")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    started = dt.datetime.now().timestamp()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.init:
        return init_action(args.cmd[0] if args.cmd else "")
    if args.agent_prompt:
        command = args.cmd[0] if args.cmd else "<project test command>"
        print(
            f'Before claiming done, run:\ndonecheck --cmd "{command}"\n\n'
            "If it fails, fix the work and rerun it. Include the DONECHECK.md status in your final answer."
        )
        return 0

    base_commit = merge_base(args.base) if args.base else None
    paths = [Path(p) for p in git_output(["ls-files"]).splitlines()] if args.all else changed_files(args.base, base_commit)
    excludes = (*DEFAULT_EXCLUDES, *tuple(args.exclude))
    findings = scan(paths, excludes)
    commands = [run(command) for command in args.cmd]
    skip_reasons = list(args.skip_reason)
    if paths and not commands and not skip_reasons:
        skip_reasons.append("no verification command supplied")
    current_hash = evidence_hash(stale_input_files(paths), commands, base_commit)
    receipt_path = None if args.write == "-" else Path(args.write)
    proof_paths = [path for path in paths if not receipt_path or path.resolve() != receipt_path.resolve()]
    findings += proof_file_findings(proof_paths, current_hash, base_commit)
    findings = proof_findings(findings, commands, paths)
    elapsed = dt.datetime.now().timestamp() - started
    status = assess([] if args.no_fail_on_findings else findings, commands, paths, skip_reasons)
    body = receipt(
        findings,
        commands,
        paths,
        elapsed,
        evidence_hash=current_hash,
        base_ref=args.base,
        base_commit=base_commit,
        skip_reasons=skip_reasons,
        status=status,
    )

    if args.write == "-":
        print(body, end="")
    else:
        Path(args.write).write_text(body, encoding="utf-8")
    write_github_step_summary(body)

    if args.write != "-":
        print(summary(status, findings, commands, skip_reasons), end="")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("\n".join(github_annotations(findings)))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
