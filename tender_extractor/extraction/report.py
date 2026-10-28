"""Conversion report: status, errors, per-page text coverage and table layout."""

import json
from pathlib import Path
from typing import Optional

REPORT_FILE = "report.json"


def build_segment_report(result, name: str, kind: str, first: int, last: int, seconds: float) -> dict:
    """
    Build a report dictionary for a single segment conversion result.
    
    Args:
        result: The conversion result object containing status, errors, and document.
        name: The name of the segment.
        kind: The kind of segment (e.g., "native" or "scanned").
        first: The first page number of the segment.
        last: The last page number of the segment.
        seconds: The time taken for the conversion of this segment.
    Returns:
        A dictionary containing the report for this segment.
    """
    doc = result.document
    tables = _table_stats(doc)
    return {
        "name": name,
        "kind": kind,
        "first_page": first,
        "last_page": last,
        "status": result.status.value,
        "seconds": round(seconds, 1),
        "errors": [
            {"component": e.component_type.value, "message": e.error_message}
            for e in result.errors
        ],
        "pages": _page_stats(doc),
        "tables": tables,
    }


def _page_stats(doc) -> list:
    """
    Count the number of text characters on each page of the document.
    
    Args:
        doc: The document object containing pages and items.
    Returns:
        A list of dictionaries, each containing the page number and the count of text characters on that
    """
    chars = {}
    for item, _ in doc.iterate_items():
        text = getattr(item, "text", "") or ""
        for prov in getattr(item, "prov", []):
            chars[prov.page_no] = chars.get(prov.page_no, 0) + len(text)
    for table in doc.tables:
        for cell in table.data.table_cells:
            for prov in table.prov:
                chars[prov.page_no] = chars.get(prov.page_no, 0) + len(cell.text)
    return [
        {"page": page_no, "text_chars": chars.get(page_no, 0)}
        for page_no in sorted(doc.pages)
    ]


def _table_stats(doc) -> list:
    """
    Extract table statistics from the document.
    
    Args:
        doc: The document object containing tables.
    Returns:
        A list of dictionaries, each containing the pages, number of rows, number of columns, and the first row of each table.
    """
    tables = []
    for table in doc.tables:
        data = table.data
        first_row = [c.text for c in data.table_cells if c.start_row_offset_idx == 0]
        tables.append(
            {
                "pages": sorted({p.page_no for p in table.prov}),
                "num_rows": data.num_rows,
                "num_cols": data.num_cols,
                "first_row": first_row,
            }
        )
    return tables


def find_multipage_tables(tables: list) -> list:
    """Tables on consecutive pages with the same column count: likely one split table.

    Docling converts each page fragment separately and does not merge them, so
    these are only reported. A repeated first row suggests a repeated header.

    Args:
        tables: List of table reports, each with pages, num_rows, num_cols, and first_row.
    Returns:
        A list of multipage table reports, each with pages, num_cols, and repeated_header
    """
    found = []
    ordered = sorted(tables, key=lambda t: t["pages"][0] if t["pages"] else 0)
    for prev, cur in zip(ordered, ordered[1:]):
        if (
            prev["pages"] and cur["pages"]
            and prev["num_rows"] and cur["num_rows"]
            and cur["pages"][0] == prev["pages"][-1] + 1
            and prev["num_cols"] == cur["num_cols"]
        ):
            found.append(
                {
                    "pages": [prev["pages"][-1], cur["pages"][0]],
                    "num_cols": cur["num_cols"],
                    "repeated_header": prev["first_row"] == cur["first_row"],
                }
            )
    return found


def generate_report(
    output_dir: Path, pdf_path: Path, segments: list, seconds: float, errors: Optional[list] = None,
) -> dict:
    """
    Build the combined report, write it to report.json and return it.

    Args:
        output_dir: Directory to save the report.
        pdf_path: Path to the original PDF file.
        segments: List of segment reports (empty if no segment could be converted).
        seconds: Total time taken for the extraction process.
        errors: Extra errors not tied to a segment, e.g. the PDF could not be read.
    Returns:
        A dictionary with status, errors, segments, and multipage tables. With no
        segments the status is "failure".
    """
    statuses = {s["status"] for s in segments}
    status = "success" if statuses == {"success"} else (
        "failure" if statuses <= {"failure"} else "partial_success"
    )
    tables = [t for s in segments for t in s.get("tables", [])]

    report = {
        "source": str(pdf_path),
        "status": status,
        "seconds": round(seconds, 1),
        "errors": list(errors or []) + [e for s in segments for e in s["errors"]],
        "segments": segments,
        "multipage_tables": find_multipage_tables(tables),
    }

    report_path = output_dir / REPORT_FILE
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
