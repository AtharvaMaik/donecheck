# Contributing

DoneCheck is intentionally small: one Python file, no runtime dependencies, and checks that are easy to explain.

## Good Contributions

- real AI-code failure patterns that DoneCheck should catch
- false positives with a small example
- GitHub Action friction
- README or install friction

## Local Check

```bash
python -m unittest -v
python donecheck.py --all --cmd "python -m unittest -v"
```

Keep new rules boring and specific. If a check needs a parser, model call, config file, or dependency, open an issue first.
