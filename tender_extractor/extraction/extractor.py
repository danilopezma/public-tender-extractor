"""Concurrency extraction: reads the meeting record and builds the offers and the issues."""

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pdfplumber

from tender_extractor.extraction import narrative
from tender_extractor.extraction.narrative import LLMError
from tender_extractor.extraction.pdf import (
    cell_reader, derotate, find_annexes, native_pages, upright_words,
)
from tender_extractor.extraction.tables import (
    MONEY_FIELDS, OfferRow, RankingRow, parse_amount, parse_offers_page, parse_ranking,
)
from tender_extractor.models import Bidder, Issue, Offer, Tender
from tender_extractor.validation import validate

POINT_FIELDS = ("price_points", "quality_points", "total_points")


@dataclass
class Extraction:
    """Result of the extraction: the tender, one offer per lot/order/bidder and the issues."""

    tender: Optional[Tender]
    offers: List[Offer] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)


def extract_concurrency(pdf_path: Path) -> Extraction:
    """Extract the concurrency from a tender meeting record PDF.

    Problems never stop the run: they become issues and the value stays None. The extracted
    data is then validated (coherence checks, reported and never corrected). The expediente
    and the abnormally-low flags need the LLM; if it is down the run still ends, with one
    LLM_UNAVAILABLE issue.

    Args:
        pdf_path: Meeting record PDF.

    Returns:
        The tender (None if its number could not be read), the offers and the issues, both
        from the extraction and from the validation.
    """
    issues: List[Issue] = []

    with tempfile.TemporaryDirectory() as tmp:
        # 1. Read the PDF: upright copy, annexes and narrative text -----------
        upright = Path(tmp) / "upright.pdf"
        derotate(pdf_path, upright)
        pages = native_pages(upright)
        with pdfplumber.open(upright) as pdf:
            # Find the anexes: Annex 1 (offers) and Annex 2 (order of prelation)
            annexes = find_annexes(pdf, pages)
            # Get the narrative text: all pages before any annex, skipping scanned pages
            text = "\n".join(pdf.pages[n - 1].extract_text() or "" for n in pages
                             if all(n < annex.start for annex in annexes.values()))
            # Report the scanned pages that have no text layer
            scanned = [n for n in range(1, len(pdf.pages) + 1) if n not in pages]
            if scanned:
                issues.append(Issue(code="PAGES_NOT_READ", field="pages", message=(
                    f"Pages {scanned[0]}-{scanned[-1]} have no text layer (scanned): not read")))

            # 2. Read the tables: offers (Annex 1) and ranking (Annex 2)
            rows: List[OfferRow] = []
            for number in annexes.get(1, []):
                page = pdf.pages[number - 1]
                stamp = [c for c in page.chars if not c["upright"]]
                try:
                    rows += parse_offers_page(upright_words(page), page.vertical_edges,
                                              page.horizontal_edges, number,
                                              cell_reader(upright, number), stamp)
                except ValueError as exc:
                    issues.append(Issue(code="PAGE_UNREADABLE", field="page",
                                        message=f"Annex 1 page {number}: {exc}"))
            ranking: List[RankingRow] = parse_ranking([(n, upright_words(pdf.pages[n - 1])) for n in annexes.get(2, [])])
    if not rows:
        issues.append(Issue(code="NO_OFFERS", message="No offers table (Annex 1) could be read"))

    # 3. Build the offers -----------------------------------------------------
    offers = _build_offers(rows, ranking, issues)

    # 4. Validate: coherence checks, reported and never corrected -------------
    issues += validate(offers, ranking)

    # 5. Read the prose with the LLM: expediente and abnormally low offers ----
    tender, llm_reachable = _read_tender(text, issues)
    if llm_reachable:
        _flag_abnormally_low(text, offers, issues)
    return Extraction(tender, offers, issues)


def _build_offers(rows: List[OfferRow], ranking: List[RankingRow], issues: List[Issue]) -> List[Offer]:
    """Turn the raw table rows into offers, reporting what cannot be turned.

    Args:
        rows: Raw rows of the offers table.
        ranking: Rows of the order of prelation, with their lot.
        issues: List where problems are appended.

    Returns:
        One Offer per row that has a bidder. A missing or partly read figure stays None.
    """
    by_bidder = {(r.lot, r.tax_id): r for r in ranking}
    offers, previous = [], None
    for row in rows:
        # 1. A bidder cell split by a page break is taken from the previous row ----------------
        if row.tax_id is None and previous and previous.lot == row.lot:
            for name in ("tax_id", "bidder") + POINT_FIELDS:
                setattr(row, name, getattr(previous, name))
            issues.append(Issue(code="BIDDER_INHERITED", lot=row.lot, order=row.order,
                                bidder=row.tax_id, message=f"Page {row.page}: bidder and points "
                                "taken from the previous row (table split by a page break)"))
        previous = row
        if row.bidder is None:
            issues.append(Issue(code="BIDDER_MISSING", lot=row.lot, order=row.order,
                                message=f"Page {row.page}: no bidder for this row"))
            continue

        # 2. Parse the figures, strictly --------------------------------------
        values = {}
        for name in MONEY_FIELDS + POINT_FIELDS:
            raw = getattr(row, name)
            try:
                values[name] = parse_amount(raw or "", decimals=2 if name in MONEY_FIELDS else None)
            except ValueError:
                issues.append(Issue(code="FIGURE_UNREADABLE", lot=row.lot, order=row.order,
                                    bidder=row.tax_id, field=name,
                                    message=f"Page {row.page}: {name} is {raw!r}"))

        # 3. Match the order of prelation and build the offer -----------------
        rank = by_bidder.get((row.lot, row.tax_id))
        if rank is None:
            issues.append(Issue(code="RANKING_NOT_FOUND", lot=row.lot, order=row.order,
                                bidder=row.tax_id, message="Bidder not in the order of prelation"))
        offers.append(Offer(
            lot=row.lot, order=row.order, bidder=Bidder(name=row.bidder, tax_id=row.tax_id),
            ranking=rank.ranking if rank else None,
            proposed_awardee=(rank.ranking == 1) if rank else None, **values,
        ))
    return offers


def _read_tender(text: str, issues: List[Issue]):
    """Read the expediente: fields by LLM, meeting date by pattern.

    Args:
        text: Narrative text of the meeting record.
        issues: List where problems are appended.

    Returns:
        (tender, reachable): the Tender (None without a file number) and whether the LLM answered.
    """
    fields, reachable = {"file_number": None, "subject": None, "contracting_authority": None}, True
    try:
        fields = narrative.tender_fields(text[:3000])
    except LLMError as exc:
        reachable = False
        issues.append(Issue(code="LLM_UNAVAILABLE", field="llm", message=(
            f"{exc}. Expediente and abnormally-low flags not extracted; start Ollama and run again")))
    date = narrative.meeting_date(text)
    for name, value in list(fields.items()) + [("meeting_date", date)]:
        if value is None:
            issues.append(Issue(code="TENDER_FIELD_MISSING", field=name,
                                message=f"{name} not found in the meeting record's text"))
    tender = Tender(meeting_date=date, **fields) if fields["file_number"] else None
    return tender, reachable


def _flag_abnormally_low(text: str, offers: List[Offer], issues: List[Issue]) -> None:
    """Mark the offers that the meeting record says are presumed abnormally low (changed in place).

    Only the offers of the named bidder whose order is among the named positions are marked;
    the others stay None, because not being mentioned is not a statement.

    Args:
        text: Narrative text of the meeting record.
        offers: Offers to mark.
        issues: List where problems are appended.
    """
    def _key(name):
        return re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()

    for paragraph in narrative.abnormal_paragraphs(text):
        try:
            findings = narrative.abnormal_findings(paragraph)
        except LLMError as exc:
            issues.append(Issue(code="LLM_UNAVAILABLE", field="abnormally_low", message=str(exc)))
            return
        for finding in findings:
            for offer in offers:
                if _key(offer.bidder.name) == _key(finding["bidder_name"]) and (
                        not finding["positions"] or offer.order in finding["positions"]):
                    offer.abnormally_low = True
                    offer.abnormally_low_positions = finding["positions"]
