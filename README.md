# public-tender-extractor

Extracts structured data from public tender documents (minutes, specifications, awards) from PDFs.

## Structure

```
tender_extractor/
├── extraction/   # PDF reading and raw field extraction
├── models/       # tender data models
├── validation/   # validation and normalization
└── export/       # result export (JSON, CSV)
data/             # sample documents (not versioned)
tests/
```

Pipeline: `extraction → models → validation → export`. Each step depends only on the previous one.

| Folder | Responsibility |
| --- | --- |
| `extraction/` | Reads PDFs with `pdfplumber` and pulls out raw text, tables and candidate fields (contracting authority, amounts, dates, bidders). Output has no quality guarantees. |
| `models/` | Defines the data shape with `pydantic` (e.g. `Tender`, `Bidder`, `Award`): fields, types and required values. Shared by all other folders. |
| `validation/` | Cleans and checks extracted data: parses amounts and dates, cross-checks consistency (e.g. the awardee is among the bidders) and flags missing or doubtful fields. |
| `export/` | Writes validated models to JSON, CSV or other formats. |

## Setup

This is a regular Python project, not an installable library.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Tests

```bash
pytest
```

## Usage

```bash
python -m tender_extractor.extraction path/to/tender.pdf [--output-dir output]
```

Writes to `output/<pdf name>/`:

- `native_pXX-pYY.json` / `.md`: Docling document (intermediate representation) and Markdown for each run of pages with a text layer.
- `scanned_pXX-pYY.json` / `.md`: the same for scanned pages, converted with forced full-page OCR.
- `report.json`: status, conversion errors (also logged), per-page text counts, tables and multipage table candidates.

Conversion errors never abort the run; they are logged and stored in the report.

`pytest.ini` adds the project root to the import path, so no installation is needed.

## Roadmap

### Phase 1 — Initialization (done)

- Repository and Python environment (`.venv`)
- `.gitignore`, `requirements.txt` and an initial README
- Basic package layout separating extraction, models, validation and export
- Smoke test to confirm the package imports

### Phase 2 — Document extraction (done)

End-to-end PDF reading with Docling, saving the intermediate representation and a conversion report. Concurrency/lot interpretation is not done yet.

Findings on the sample minutes (50 pages: 12 native, 38 scanned annex):

- **Scanned annex:** the scanned pages carry a 22-character watermark text layer, so Docling's default OCR skips them and returns almost nothing (empty tables). Pages are now classified with `pdfplumber` and scanned runs are converted with `force_full_page_ocr`. This recovers the text and tables (about 1.6 s/page on Apple GPU). OCR is imperfect (e.g. "ESFIBRILADOR"), and a few pages (21, 28, 42) still come out nearly empty.
- **Multipage tables:** Docling does not merge tables across pages; each page fragment is a separate table. The report lists consecutive-page tables with the same column count as merge candidates (8 in the sample). A repeated header row is only a weak signal, so merging is left for a later phase.
- **Segments:** each segment is saved as its own document because `DoclingDocument.concatenate` renumbers pages.

### Phase 3 — Data model (done)

Pydantic models in `tender_extractor/models/`, independent of the PDF format:

- `Tender` (expediente), `Bidder`, `Offer` and `Issue`.
- Amounts and scores are `Decimal`. Floats are rejected, so a figure cannot pick up binary rounding error, and JSON output writes them as strings (`"12789.50"`).
- `lot` and `order` are strings kept as written (`"1.10"` is not `"1.1"`); numbers are rejected.
- Every figure on an `Offer` is optional: a missing or unreadable value stays `None` and becomes an `Issue`, never a guess.
- Unknown fields are errors (`extra="forbid"`).
