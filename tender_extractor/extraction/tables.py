"""Tables of the meeting record: the offers annex (Annex 1) and the order of prelation (Annex 2).

Both work on word boxes (dicts with text, x0, x1, top, bottom) and drawn lines. The offers
annex has a damaged text layer: the cells with a euro sign lose characters and a margin
stamp crosses the last amount. So the euro columns are read by OCR cell by cell and the
rest comes from the text layer. The layout comes from the drawn lines.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Callable, List, Optional, Tuple

TAX_ID = re.compile(r"^(?:[A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z])$")
ORDER = re.compile(r"^\d{1,3}(?:\.\d{1,3})?$")  # lots without orders repeat the lot ("13")
INT = re.compile(r"^\d{1,3}$")
SCORE = re.compile(r"^\d{1,3},\d{1,2}$")
COLUMNS = ["lot", "order", "tax_id", "bidder", "tender_unit_price", "tender_total",
           "offered_unit_price", "offered_total", "price_points", "quality_points",
           "total_points"]
MONEY_FIELDS = ("tender_unit_price", "tender_total", "offered_unit_price", "offered_total")


@dataclass
class OfferRow:
    """One row of the offers table, as raw text."""

    page: int
    lot: str
    order: str
    tax_id: Optional[str] = None
    bidder: Optional[str] = None
    tender_unit_price: Optional[str] = None
    tender_total: Optional[str] = None
    offered_unit_price: Optional[str] = None
    offered_total: Optional[str] = None
    price_points: Optional[str] = None
    quality_points: Optional[str] = None
    total_points: Optional[str] = None


@dataclass
class RankingRow:
    """One row of the order of prelation."""

    page: int
    ranking: int
    tax_id: str
    name: str
    lot: Optional[str] = None


def parse_offers_page(
    words: List[dict],
    vertical: List[dict],
    horizontal: List[dict],
    page: int,
    ocr: Callable[[Tuple[float, float, float, float]], str],
    stamp_chars: Optional[List[dict]] = None,
) -> List[OfferRow]:
    """Read the rows of one page of the offers table.

    Args:
        words: Upright word boxes of the page.
        vertical: Vertical lines (pdfplumber edges).
        horizontal: Horizontal lines (pdfplumber edges).
        page: Page number, kept in each row.
        ocr: Function that reads a cell box (x0, top, x1, bottom) with OCR.
        stamp_chars: Characters of the margin stamp. OCR is not used on a cell they cross,
            because it can return wrong digits there without warning.

    Returns:
        One OfferRow per table row, with raw text (None where nothing was read).

    Raises:
        ValueError: The lines do not match the expected 11-column table.
    """

    def _cluster(values, tolerance=2.5):
        """
        Merge values closer than the tolerance into their average (a line drawn twice).
        Some lines are drawn twice, so the same column or row can have two close lines. The
        average is used to avoid splitting the column or row into two.
        """
        groups = []
        for value in sorted(values):
            if groups and value - groups[-1][-1] <= tolerance:
                groups[-1].append(value)
            else:
                groups.append([value])
        return [sum(g) / len(g) for g in groups]

    def _band(lines, y, limits):
        """(top, bottom) lines around y; `limits` replace a missing line at a page edge."""
        above = [v for v in lines if v < y]
        below = [v for v in lines if v > y]
        return (max(above) if above else limits[0], min(below) if below else limits[1])

    def _in_column(word, index):
        return bounds[index] <= (word["x0"] + word["x1"]) / 2 < bounds[index + 1]

    def _text(selected):
        ordered = sorted(selected, key=lambda w: (round(w["top"]), w["x0"]))
        return " ".join(w["text"] for w in ordered) or None

    # 1. Column lines: the long vertical lines --------------------------------
    length = {}
    for edge in vertical:
        length[round(edge["x0"])] = length.get(round(edge["x0"]), 0) + edge["bottom"] - edge["top"]
    longest = max(length.values(), default=0)
    bounds = _cluster([float(x) for x, total in length.items() if total >= longest * 0.4])
    if len(bounds) != len(COLUMNS) + 1:
        raise ValueError(f"expected {len(COLUMNS) + 1} column lines, found {len(bounds)}")

    # 2. Row lines, and bidder-block lines (which also cross the NIF column) ---
    coverage = {}
    for edge in horizontal:
        coverage[round(edge["top"])] = coverage.get(round(edge["top"]), 0) + edge["x1"] - edge["x0"]
    row_lines = _cluster([float(y) for y, total in coverage.items() if total > 250])
    bidder_lines = _cluster([e["top"] for e in horizontal
                             if e["x0"] <= bounds[2] + 3 and e["x1"] >= bounds[3] - 3])
    gaps = sorted(b - a for a, b in zip(row_lines, row_lines[1:]) if b - a < 30)
    if not gaps:
        raise ValueError("no row lines")
    row_height = gaps[len(gaps) // 2]

    # 3. One anchor per row: the order cell -----------------------------------
    anchors = sorted((w for w in words if ORDER.match(w["text"]) and _in_column(w, 1)),
                     key=_center)
    if not anchors:
        return []
    page_limits = (_center(anchors[0]) - row_height / 2, _center(anchors[-1]) + row_height / 2)

    # 4. Read every row -------------------------------------------------------
    rows = []
    for anchor in anchors:
        y = _center(anchor)
        top, bottom = _band(row_lines, y, (y - row_height / 2, y + row_height / 2))
        in_row = [w for w in words if top <= _center(w) <= bottom]
        lot = [w["text"] for w in in_row if _in_column(w, 0) and INT.match(w["text"])]
        if not lot:
            continue
        row = OfferRow(page=page, lot=lot[0], order=anchor["text"])

        # Euro columns by OCR. Last amount from the text layer, by OCR only outside the stamp.
        for index in (4, 5, 6):
            setattr(row, COLUMNS[index], ocr((bounds[index], top, bounds[index + 1], bottom)) or None)
        cell = (bounds[7], top, bounds[8], bottom)
        row.offered_total = _text(w for w in in_row if _in_column(w, 7))
        crossed = any(c["x0"] < cell[2] and c["x1"] > cell[0] and c["top"] < cell[3]
                      and c["bottom"] > cell[1] for c in stamp_chars or [])
        try:
            parse_amount(row.offered_total or "", decimals=2)
        except ValueError:
            if not crossed:
                row.offered_total = ocr(cell) or None

        # Bidder, tax id and points are merged over the rows of the bidder block.
        block_top, block_bottom = _band(bidder_lines, y, page_limits)
        in_block = [w for w in words if block_top <= _center(w) <= block_bottom]
        tax_ids = [w["text"] for w in in_block if _in_column(w, 2) and TAX_ID.match(w["text"])]
        row.tax_id = tax_ids[0] if tax_ids else None
        row.bidder = _text(w for w in in_block if _in_column(w, 3))
        for index in (8, 9, 10):
            setattr(row, COLUMNS[index], _text(w for w in in_block if _in_column(w, index)))
        rows.append(row)
    return rows


def parse_ranking(pages: List[Tuple[int, List[dict]]]) -> List[RankingRow]:
    """Read the order of prelation (Annex 2): lot, ranking and bidder of every row.

    Each row is anchored on its tax id. The lot is written once per lot, centered on its
    rows, so a lot ends when the ranking stops increasing and takes the label nearest to
    its rows. A lot can continue on the next page.

    Args:
        pages: (page number, upright word boxes) of every page of the annex, in order.

    Returns:
        One RankingRow per row, with its lot.
    """
    # 1. Rows and lot labels of every page ------------------------------------
    rows, positions, labels = [], [], []  # positions: (page, y) of each row
    for number, words in pages:
        anchors = sorted((w for w in words if TAX_ID.match(w["text"])), key=_center)
        centers = [_center(w) for w in anchors]
        gap = median(b - a for a, b in zip(centers, centers[1:])) if len(centers) > 1 else 14.0
        rank_x = []
        for i, anchor in enumerate(anchors):
            y = centers[i]
            line = [w for w in words if abs(_center(w) - y) <= gap / 3]
            ints = sorted((w for w in line if INT.match(w["text"]) and w["x1"] <= anchor["x0"]),
                          key=lambda w: w["x0"])
            if not ints:
                continue
            score = max((w for w in line if SCORE.match(w["text"]) and w["x0"] > anchor["x1"]),
                        key=lambda w: w["x0"], default=None)
            rank_x.append(ints[-1]["x0"])
            labels += [(number, y, w["text"]) for w in ints[:-1]]  # lot written on the row

            # The name can wrap over several lines around the row.
            low = max(y - gap * 0.75, (centers[i - 1] + y) / 2) if i else y - gap * 0.75
            high = min(y + gap * 0.75, (y + centers[i + 1]) / 2) if i + 1 < len(centers) else y + gap * 0.75
            name = sorted((w for w in words if w["x0"] >= anchor["x1"] - 1 and w is not score
                           and (score is None or w["x1"] <= score["x0"] + 0.5)
                           and low <= _center(w) <= high), key=lambda w: (round(w["top"]), w["x0"]))
            rows.append(RankingRow(number, int(ints[-1]["text"]), anchor["text"],
                                   " ".join(w["text"] for w in name)))
            positions.append((number, y))

        # Lot labels that sit alone in the lot column, left of the ranking column.
        for w in words if rank_x else []:
            if INT.match(w["text"]) and w["x1"] <= min(rank_x) \
                    and centers[0] - gap <= _center(w) <= centers[-1] + gap \
                    and not any(abs(_center(w) - c) <= gap / 3 for c in centers):
                labels.append((number, _center(w), w["text"]))

    # 2. Group the rows into lots: a lot ends when the ranking stops increasing -
    lot_of, lot, previous = [], 0, 0
    for row in rows:
        lot += row.ranking <= previous
        previous = row.ranking
        lot_of.append(lot)

    # 3. Each lot takes the label nearest to its rows --------------------------
    names = {}
    for number, y, text in labels:
        nearest = min((i for i, (p, _) in enumerate(positions) if p == number),
                      key=lambda i: abs(positions[i][1] - y))
        names.setdefault(lot_of[nearest], text)
    for row, lot in zip(rows, lot_of):
        row.lot = names.get(lot)
    return rows


def parse_amount(text: str, decimals: Optional[int] = None) -> Decimal:
    """Parse an amount written like '1.234,56 €'. No float is ever involved.

    A partly read cell (e.g. '40.6' or '455.400,0') is rejected, never turned into a number.

    Args:
        text: Text of the cell.
        decimals: Exact number of decimals required (2 for money); None accepts any.

    Returns:
        The amount as a Decimal.

    Raises:
        ValueError: The text is not a complete amount.
    """
    cleaned = text.replace("€", "").replace("\xa0", " ").strip()
    fraction = r"(?:,\d+)?" if decimals is None else rf",\d{{{decimals}}}"
    if not re.fullmatch(rf"(?:\d{{1,3}}(?:\.\d{{3}})+|\d+){fraction}", cleaned):
        raise ValueError(f"not an amount: {text!r}")
    return Decimal(cleaned.replace(".", "").replace(",", "."))


def _center(word: dict) -> float:
    """Vertical center of a word box."""
    return (word["top"] + word["bottom"]) / 2
