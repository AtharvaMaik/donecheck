# DoneCheck

Your AI coding agent says it is done. Make it prove it.

`donecheck` is a zero-dependency CLI that turns "done" into a small receipt:

- what files changed
- which cheap failure patterns were checked
- which verification commands actually ran
- whether the work is safe to hand to a human

```bash
python donecheck.py --cmd "pytest -q"
cat DONECHECK.md
```

If the diff contains unfinished placeholders, swallowed errors, obvious secret literals, unsafe `eval`, or a failing command, `donecheck` exits non-zero.

## Why

AI agents are great at sounding finished. They are less great at proving it.

DoneCheck is a boring gate for the recurring failure modes that waste review time:

- unfinished markers and placeholder phrases left in changed files
- `except: pass` and empty JavaScript `catch` blocks
- accidental literal secrets
- unsafe `eval` / `exec`
- skipped tests hidden behind a confident final answer

It is intentionally small. Keep your real linter, tests, review bot, and human reviewer. Run this first so they do not spend time on obvious misses.

## Install

Use it straight from the repo:

```bash
python donecheck.py --cmd "pytest -q"
```

Or install as a command:

```bash
pipx install git+https://github.com/AtharvaMaik/donecheck
donecheck --cmd "pytest -q"
```

## GitHub Action

```yaml
name: donecheck
on: [pull_request]

jobs:
  donecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: AtharvaMaik/donecheck@main
        with:
          command: pytest -q
```

## Agent Prompt

Tell your coding agent:

```text
Before claiming done, run:
python donecheck.py --cmd "<project test command>"

If it fails, fix the work and rerun it. Include DONECHECK.md in your final answer.
```

## Examples

Failing diff:

```python
def charge_card():
    # TODO wire Stripe later
    return True
```

Receipt:

```text
DoneCheck Receipt: FAIL
- unfinished_marker in app.py:2: # TODO wire Stripe later
```

Passing run:

```text
DoneCheck Receipt: PASS
- files checked: 4
- findings: 0
- commands: 1
```

## What It Is Not

DoneCheck is not a general linter, security scanner, or test framework. It is a fast proof-of-work floor for AI-assisted changes.

Skipped: model-based review, AST parsing, config files, dashboards. Add those when this tiny gate stops being enough.
