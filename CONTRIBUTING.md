# Contributing

Use only synthetic fixtures in tests and examples. Never add real application
documents or private fitted models. New generation behavior should include a
deterministic test and preserve the two-track privacy boundary.

Run before opening a pull request:

```bash
pytest -q
python scripts/public_release_audit.py .
```
