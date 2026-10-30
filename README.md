# public-tender-extractor

Extracts the **concurrency** of a public tender from the meeting record (*acta de la mesa de contratación*) PDF: who bid on each lot, what they offered, their scores and their ranking.

## How to run

Requirements: Python 3.9+ and [Ollama](https://ollama.com) running locally.

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

1. **Upright pages.** The offers annex is a landscape table stored with rotated text. The dominant text direction of each page gives the rotation to undo, and a temporary upright copy is used from then on.
2. **Tables, deterministic.** Columns, rows and bidder blocks come from the drawn lines and word positions, not from a model. The offers annex is a rotated landscape table with a damaged text layer, so pages are turned upright first, the euro columns are read by OCR cell by cell (RapidOCR, any platform) and the rest from the text layer.
3. **Prose, with an LLM.** (expediente fields, who is flagged as abnormally low and where). Whatever it returns must appear verbatim in the PDF text or it is dropped. If Ollama is down the run still ends, with an `LLM_UNAVAILABLE` issue.
4. **Validation.** Points add up, offered price not above tender price, offered total = unit price × quantity (quantity = tender total / tender unit price, must be a whole number), same tender price for every bidder of an order, a better rank never has fewer points, and Annex 2 agrees with Annex 1 on who bid and the total score. On the sample it finds one real discrepancy: lot 2.1 of Biotronick offers 12.886,00 × 225 = 2.899.350,00 but the document says 2.894.850,00. The tender-price check also confirms the OCR, since every bidder must show the same figure. Checks are only reported, never fixed.

### Design decisions and why

- **Exact figures.** Amounts are `Decimal`, floats are rejected, money must have exactly two decimals and a partly read cell becomes an issue, not a number. Lot and order are strings kept as written (`"1.10"` is not `"1.1"`).
- **A missing value is better than a wrong one.** Anything unreadable stays empty and goes to `incidencias.json`. Errors never stop the run, including the LLM being down (one `LLM_UNAVAILABLE` issue; the expediente and the abnormally-low flags are then missing).
- **The LLM is required but boxed in.** It only reads prose, its output is checked against the source text, and tests replace it with a fake.
- **Why `pdfplumber` and not Docling.** I started with Docling because I knew it, and it was the quickest way to a first reading. In the end it was not needed: the annexes that hold the concurrency (offers and order of prelation) are native text, so I did not need Docling to read scanned pages, and the scanned technical report is not needed for the concurrency. The only OCR left is a small one on a few damaged cells of the offers table (the euro columns), done cell by cell with RapidOCR. On top of that, on the real file Docling shifted the cells of the rotated annex, its OCR returned wrong digits under the stamp, and it took about 2 of the 4-5 minutes of a run for output the table parsers did not use. `pdfplumber` gives word boxes and the drawn lines with coordinates, which is what a deterministic parser needs.

## Tools

| Job | Tool |
| --- | --- |
| Words, drawn lines, text of each page | `pdfplumber` |
| Page rotation, page rendering for OCR | `pypdfium2` |
| OCR of table cells | RapidOCR (ONNX, one cell at a time, text recognition only) |
| Prose (expediente, abnormally low offers) | Ollama with Qwen2.5-7B-Instruct, JSON-schema output, temperature 0 |
| Data model | `pydantic` |
| Excel | `openpyxl` |

## Cost per document

No paid model is used, so there is no API cost. The 50-page sample takes about 2-3 minutes on a laptop: derotating and laying out the 12 pages that have text, about 500 OCR calls (~0.03 s each) and two LLM calls. If the local model were replaced by a paid API, the cost would still be a fraction of a cent per document: two short prompts, about 1,000 and 300 input tokens.

## Processing 160 minutes from different organisms

What would fail, and what I would change:

- **The layout is hard-coded.** The offers table must have 11 columns in a fixed order, and the annexes are found by a line starting with `ANEXO n` (1 = offers, 2 = prelation). Other organisms will name and order the columns differently. I would find the table by its header text and map each column from it, not by position.
- **Scanned pages.** Pages without a text layer are not read (here, the technical report). A fully scanned record would give nothing. It needs full-page OCR plus table-structure recognition, which is where a layout model like Docling is stronger, so I would use it for that case only.
- **The 7B model.** It is enough for two short passages here; other styles of text may need a larger model or an API, still at a negligible cost per document.
- **Time.** About 2-3 minutes each is roughly 5-8 hours for 160 sequentially. Documents are independent, so a batch runner in parallel, with one output folder per document and a summary of issues per document, fixes it.
- **Trust.** I have tested on one record. With 160 I would build a small labelled set and measure per-field accuracy, and review the issues first to find the layouts that break.