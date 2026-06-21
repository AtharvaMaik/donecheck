# DoneCheck Launch Kit

Goal: get developers to understand, try, and star DoneCheck in under one minute.

Repo: https://github.com/AtharvaMaik/donecheck

## Primary Hook

Your AI coding agent says it is done. Make it prove it.

## Show HN

Title:

```text
Show HN: DoneCheck - make AI coding agents prove they are done
```

Post:

```text
I built DoneCheck after getting tired of AI coding agents confidently saying work was finished without showing what they actually verified.

It is a zero-dependency Python proof gate:

- scans changed files for common AI-code failure patterns
- runs the verification command you choose
- fails if there is no evidence
- writes a small DONECHECK.md receipt
- works locally, in GitHub Actions, and as a prompt/skill for Claude Code, Codex, and Cursor

The goal is not to replace tests, linters, or review. It is the cheap first gate before a human wastes time on obvious misses.

Repo: https://github.com/AtharvaMaik/donecheck
```

## X / LinkedIn Short Post

```text
I launched DoneCheck.

Your AI coding agent says it is done.
DoneCheck makes it prove it.

- zero dependencies
- scans changed files
- runs your verification command
- fails with no evidence
- writes DONECHECK.md
- works in GitHub Actions

https://github.com/AtharvaMaik/donecheck
```

## Reddit / Community Post

```text
I made a tiny proof gate for AI coding agents.

The problem: agents often end with confident summaries, but the human still has to ask: what changed, what was checked, and did tests actually run?

DoneCheck is intentionally small:

- one Python file
- no dependencies
- scans changed files for common AI-generated failure patterns
- runs your chosen command
- fails if nothing was checked
- writes a DONECHECK.md receipt

It is not a replacement for tests or review. It is a cheap first gate before review.

Repo: https://github.com/AtharvaMaik/donecheck
```

## Places To Submit

- Hacker News: Show HN
- Trendshift: submit repository
- GitHub topic communities: `ai-agents`, `ai-coding`, `claude-code`, `codex`
- Reddit: r/ClaudeAI, r/OpenAI, r/programming, r/github, r/devtools
- Discord/Slack communities for Cursor, Claude Code, Codex, and agentic coding

## Launch Checklist

- GitHub CI green
- latest release points to current README
- README first screen shows hook, badges, and demo
- pin action examples to latest tag
- reply to every comment in first 24 hours
- ask early users for real failure patterns to add
