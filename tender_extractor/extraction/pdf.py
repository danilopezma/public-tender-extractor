"""PDF reading helpers: page rotation, annexes, text layer and cell-level OCR."""

import math
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from PIL import ImageOps

# Pages with fewer characters of text than this are scans and are not read.
MIN_TEXT_CHARS = 100


def derotate(pdf_path: Path, output_path: Path) -> None:
    """Write a copy of the PDF with its rotated pages turned upright.

    Landscape tables in portrait pages are stored with rotated text; the dominant text
    direction of a page tells the rotation to undo. Page numbers do not change.

    Args:
        pdf_path: PDF to read.
        output_path: Where the upright copy is written.
    """
    # 1. Rotation of every page with a text layer -----------------------------
    with pdfplumber.open(pdf_path) as plumber:
        rotations = {}
        for number in native_pages(pdf_path):
            angles = Counter(
                round(math.degrees(math.atan2(c["matrix"][1], c["matrix"][0])) / 90) % 4 * 90
                for c in plumber.pages[number - 1].chars if c["matrix"][0] or c["matrix"][1]
            )
            rotations[number] = angles.most_common(1)[0][0] if angles else 0

    # 2. Rotate those pages and save the copy ---------------------------------
    document = pdfium.PdfDocument(str(pdf_path))
    for number, rotation in rotations.items():
        page = document[number - 1]
        page.set_rotation((page.get_rotation() + rotation) % 360)
    document.save(str(output_path))


def find_annexes(pdf, pages: List[int]) -> Dict[int, range]:
    """Find the page range of each annex (a line starting with 'ANEXO n').

    Args:
        pdf: Open pdfplumber document.
        pages: Numbers of the pages with a text layer, where to search.

    Returns:
        Page range of each annex, keyed by annex number; it ends where the next one starts.
    """
    starts: Dict[int, int] = {}
    for number in pages:
        for line in (pdf.pages[number - 1].extract_text() or "").splitlines():
            match = re.match(r"^ANEXO\s+(\d+)\b", line.strip())
            if match:
                starts.setdefault(int(match.group(1)), number)
    ordered = sorted(starts.items(), key=lambda item: item[1])
    ends = [first for _, first in ordered[1:]] + [len(pdf.pages) + 1]
    return {annex: range(first, end) for (annex, first), end in zip(ordered, ends)}


def cell_reader(pdf_path: Path, page_number: int, scale: int = 4) -> Callable[[Tuple], str]:
    """Build a function that reads one table cell of a page with OCR (RapidOCR, any platform).

    Each cell is read alone, as one line of text, so neighbouring cells are never merged.
    The cell is trimmed inside its borders and padded with white so the drawn lines are not
    read as characters.

    Args:
        pdf_path: PDF with upright pages.
        page_number: Page number, starting at 1.
        scale: Rendering scale; 4 is about 290 dpi.

    Returns:
        A function that takes a cell box (x0, top, x1, bottom in PDF points) and returns the
        text read, or an empty string.
    """
    from rapidocr import RapidOCR

    inset = 3
    image = pdfium.PdfDocument(str(pdf_path))[page_number - 1].render(scale=scale).to_pil().convert("L")
    engine = RapidOCR()

    def read(box):
        x0, top, x1, bottom = box
        crop = image.crop((int((x0 + inset) * scale), int((top + inset) * scale),
                           int((x1 - inset) * scale), int((bottom - inset) * scale)))
        crop = ImageOps.expand(crop, border=20, fill=255).convert("RGB")
        result = engine(np.array(crop), use_det=False, use_cls=False, use_rec=True)
        return " ".join(result.txts).strip() if result.txts else ""

    return read


def native_pages(pdf_path: Path) -> List[int]:
    """Numbers of the pages that have a text layer (the rest are scans).

    Args:
        pdf_path: PDF to check.
    """
    document = pdfium.PdfDocument(str(pdf_path))
    return [n for n in range(1, len(document) + 1)
            if document[n - 1].get_textpage().count_chars() >= MIN_TEXT_CHARS]


def upright_words(page) -> List[dict]:
    """Words of a pdfplumber page, ignoring margin stamps and watermarks (not upright)."""
    return page.filter(lambda o: o["object_type"] != "char" or o["upright"]).extract_words()
