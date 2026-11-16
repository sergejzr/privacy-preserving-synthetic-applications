# Privacy-preserving synthetic applications

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).

Local-first Python package for generating realistic, fully fictional application
dossiers while keeping sensitive reference corpora and fitted population models
outside the public package.

## Pipeline

The package has two top-level phases:

1. **Fit** — analyze the private PDF corpus and fit coarsened structural and
   dossier models without exporting source text.
2. **Generate** — sample structure, generate fictional profiles with a local
   LLM, run a profile-quality pass, render PDFs, and validate the result.

Internally, generation is:

`profiles → quality pass → document text → PDF/scan rendering → audit`

The package also contains a small license-independent conditional table model.
It learns only coarsened structural fields (page bucket, layout, photo flag,
image density and document count), never source PDF text:

```bash
synthetic-apps fit-table /private/structure_profiles \
  /private/models/structural_table_model.json
synthetic-apps sample-table /private/models/structural_table_model.json \
  --count 20 --output /tmp/structural_samples.json
```

This is an optional diagnostic/modeling layer; the established structural and
dossier models remain the authoritative generation plans. The validator also
rejects substantial duplicate page content so rendering regressions do not
silently produce repeated pages.

## Privacy boundary

Never commit original applications, private structural profiles, fitted private
models, API keys, OpenWebUI exports, or generated dossiers derived from private
data. Keep them outside the repository and run the public-release audit before
publishing.

## Installation

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

## Fit private models

```bash
synthetic-apps analyze --input /private/original_applications \
  --output /private/structure_profiles
synthetic-apps fit-structural /private/structure_profiles \
  --output /private/models/structural_model.json
synthetic-apps fit-dossier /private/structure_profiles \
  --output /private/models/dossier_model.json
```

## Generate a synthetic dataset

Configure the local model through environment variables and use a public-safe
configuration template:

```bash
export SYNTH_LLM_BASE_URL=http://127.0.0.1:3000/v1
export SYNTH_LLM_MODEL=local-model
export SYNTH_LLM_API_KEY=local-only-token

synthetic-apps generate \
  --config config.public.example.yaml \
  --structural-model /private/models/structural_model.json \
  --dossier-model /private/models/dossier_model.json \
  --count 5 --force
```

The topic is configurable in YAML or directly on the command line:

```bash
synthetic-apps generate ... \
  --title 'Wissenschaftliche Position zur Drachenforschung im Siebengebirge' \
  --organization 'Fiktives Institut für Drachenforschung Siebengebirge' \
  --count 20
```

The output contains fictional profiles, `Ausdruck.pdf`, `Bewerbung.pdf`,
document evidence, render audit data, and validator results.

## Tests and release audit

```bash
pytest -q
python scripts/public_release_audit.py .
```

The audit intentionally fails in a working tree containing private corpus/model
directories. Build a clean public checkout or staging directory before release.

## Prior art

This is related to, but different from, tabular synthetic-data systems such as
[SDV](https://github.com/sdv-dev/SDV) and document rewriting systems such as the
[AWS Synthetic Document Generator](https://github.com/aws-samples/sample-synthetic-document-generator).
This project focuses on learned application-dossier populations: document
sequences, page counts, attachments, local-model text, quality review, and PDF
scan variation.

## Status

Experimental research software. Generated documents are fictional test data and
must be reviewed before external distribution.
