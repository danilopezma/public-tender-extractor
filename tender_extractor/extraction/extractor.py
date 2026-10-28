"""PDF to Docling conversion, with the intermediate representation saved to disk.

The PDF is split into contiguous segments: pages with a native text layer and
scanned pages. Docling skips OCR on pages that carry any text layer, even a
tiny watermark, so scanned segments are converted with full-page OCR forced.
Each segment is saved as its own Docling document, keeping the original page
numbers (DoclingDocument.concatenate would renumber them).
"""

import logging
import time
from pathlib import Path
from typing import List, Tuple

import pdfplumber
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import OcrAutoOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from tender_extractor.extraction.report import build_segment_report, generate_report

logger = logging.getLogger(__name__)

# Pages with fewer native text characters than this are treated as scanned.
SCANNED_TEXT_THRESHOLD = 100

Segment = Tuple[int, int, str]  # (first_page, last_page, "native" | "scanned")


def extract_document(pdf_path: Path, output_dir: Path) -> dict:
    """Convert a PDF and write one document/markdown pair per segment plus report.json.

    Conversion errors are logged and stored in the report instead of being raised,
    so partial results stay inspectable. Returns the report.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Get page segments by kind (native or scanned) -----------------------------------
    started = time.time()
    try:
        segments = detect_segments(pdf_path)
    except Exception as exc:
        logger.exception("Cannot read %s", pdf_path)
        error = {"component": "pdf-reader", "message": repr(exc)}
        # Generate failure report
        return generate_report(output_dir, pdf_path, [], time.time() - started, errors=[error])

    # 2. Convert each segment and save as JSON/Markdown -----------------------------------
    native_converter = _build_converter(force_ocr=False)
    scanned_converter = _build_converter(force_ocr=True)
    segment_reports = []
    for first, last, kind in segments:
        name = f"{kind}_p{first}-p{last}"
        logger.info(f"Converting {name} (pages {first}-{last})")
        converter = native_converter if kind == "native" else scanned_converter
        seg_started = time.time()
        try:
            result = converter.convert(pdf_path, page_range=(first, last), raises_on_error=False)
        except Exception as exc:
            logger.exception("Segment %s failed", name)
            segment_reports.append(
                {
                    "name": name, "kind": kind, "first_page": first, "last_page": last,
                    "status": "failure",
                    "errors": [{"component": "converter", "message": repr(exc)}],
                }
            )
            continue

        for error in result.errors:
            logger.error(
                f"Conversion error in {name} [{error.component_type.value}]: {error.error_message}",
            )
        if result.status != ConversionStatus.SUCCESS:
            logger.warning(f"Segment {name} finished with status {result.status.value}")

        result.document.save_as_json(output_dir / f"{name}.json")
        result.document.save_as_markdown(output_dir / f"{name}.md")
        segment_reports.append(
            build_segment_report(result, name, kind, first, last, time.time() - seg_started)
        )

    # 3. Generate final report  --------------------------------------------------
    report = generate_report(output_dir, pdf_path, segment_reports, time.time() - started)
    
    logger.info(f"Generated report for {pdf_path} in {output_dir}")
    return report


def detect_segments(pdf_path: Path) -> List[Segment]:
    """
    Group consecutive pages by whether they are native or scanned.

    Args:  
        pdf_path: Path to the PDF file.
    Returns:
        A list of segments, each represented as a tuple (first_page, last_page, kind),
        where kind is either "native" or "scanned".
    """
    segments: List[Segment] = []
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            kind = "native" if len(page.extract_text() or "") >= SCANNED_TEXT_THRESHOLD else "scanned"
            if segments and segments[-1][2] == kind:
                segments[-1] = (segments[-1][0], number, kind)
            else:
                segments.append((number, number, kind))
    return segments


def _build_converter(force_ocr: bool = False) -> DocumentConverter:
    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = True
    if force_ocr:
        options.ocr_options = OcrAutoOptions(force_full_page_ocr=True, lang=["es-ES"])
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
