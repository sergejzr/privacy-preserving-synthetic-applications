# Security and privacy

Do not open issues or pull requests containing original applications, names,
addresses, credentials, private model files, or local-model logs.

Before publishing an artifact, run:

```bash
python scripts/public_release_audit.py .
```

The audit is a guardrail, not a legal or privacy guarantee. Review generated
PDFs manually and keep private reference data outside the repository.
