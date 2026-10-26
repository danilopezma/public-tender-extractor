# public-tender-extractor

Extracts structured data from public tender documents from PDFs.

## Structure

```
tender_extractor/
├── extraction/   # PDF reading and raw field extraction
├── models/       # tender data models
├── validation/   # validation and normalization
└── export/       # result export (JSON, CSV)
data/             # sample documents
tests/
```

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Tests

```bash
pytest
```

## Status

Phase 1: initial project structure.
