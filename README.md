# public-tender-extractor

Extracts the **concurrency** of a public tender from the meeting record PDF (acta de la mesa de contratación): who bid on each lot, what they offered, their scores and ranking.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ollama pull hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M   # local LLM, Ollama must be running
python main.py [path/to/meeting_record.pdf] [--output-dir output]
pytest
```

Writes to `output/`:

- `concurrencia.json` and `concurrencia.xlsx`: the expediente and one row per lot, order and bidder.
- `incidencias.json`: what could not be read or does not add up. Nothing is corrected silently.

## How it works

```
main.py
tender_extractor/
├── extraction/
│   ├── pdf.py        # upright pages, annexes, cell OCR
│   ├── tables.py     # offers table (Annex 1) and order of prelation (Annex 2)
│   ├── narrative.py  # prose: expediente, meeting date, abnormally low offers (LLM)
│   └── extractor.py  # puts it together
├── validation.py     # coherence checks on the extracted data
├── models/schema.py  # Tender, Bidder, Offer, Issue
└── export/writers.py # json and xlsx
```

- **Tables are deterministic.** Columns, rows and bidder blocks come from the drawn lines and word positions, not from a model. The offers annex is a rotated landscape table with a damaged text layer, so pages are turned upright first, the euro columns are read by OCR cell by cell (RapidOCR, any platform) and the rest from the text layer.
- **The LLM only reads prose** (expediente fields, who is flagged as abnormally low and where). Whatever it returns must appear verbatim in the PDF text or it is dropped. If Ollama is down the run still ends, with an `LLM_UNAVAILABLE` issue.
- **Validation, reported and never fixed** (`validation.py`): points add up, offered price not above tender price, offered total = unit price × quantity (quantity = tender total / tender unit price, must be a whole number), same tender price for every bidder of an order, a better rank never has fewer points, and Annex 2 agrees with Annex 1 on who bid and the total score. On the sample it finds one real discrepancy: lot 2.1 of Biotronick offers 12.886,00 × 225 = 2.899.350,00 but the document says 2.894.850,00. The tender-price check also confirms the OCR, since every bidder must show the same figure.
- **Figures are exact.** Amounts are `Decimal`, floats are rejected, money needs exactly two decimals, and a partly read cell becomes an issue instead of a number.
- **Lot and order are strings** kept as written (`"1.10"` is not `"1.1"`).

## Why `pdfplumber` and not Docling

I started with Docling because I knew it. On the real file it shifted the cells of the rotated annex, its OCR returned wrong digits under a margin stamp, and it took about 2 of the 4-5 minutes of a run for output the table parsers did not use. `pdfplumber` gives word boxes and the drawn lines with coordinates, which is what a deterministic parser needs.

## Limits

- Tested on one meeting record file. The offers parser expects 11 columns in a fixed order.
- Scanned pages (here the technical report, Annex 3) are not read; they are reported as an issue. That report holds the quantity per order and the breakdown of the qualitative points, which a validation step would need.
- Not implemented: page of origin per figure, other organisms (160 meeting records).
- Assumptions: `proposed_awardee` is `ranking == 1`; `abnormally_low` is true only for the offers the text names.
