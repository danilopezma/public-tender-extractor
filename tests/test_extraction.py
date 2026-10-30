from decimal import Decimal

import pytest

from tender_extractor.extraction import extractor, narrative
from tender_extractor.extraction.tables import OfferRow, RankingRow, parse_amount, parse_offers_page, parse_ranking


def word(text, x0, top, x1=None):
    return {"text": text, "x0": x0, "x1": x1 or x0 + 8 * len(text), "top": top, "bottom": top + 9}


# --- amounts ---------------------------------------------------------------------

def test_parse_amount_keeps_every_digit():
    assert str(parse_amount("1.234,56 €")) == "1234.56"
    assert str(parse_amount("969,00", decimals=2)) == "969.00"


@pytest.mark.parametrize("text", ["40.6", "124.950,", "", "1,234,56", "14.233 78"])
def test_parse_amount_rejects_partly_read_cells(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_money_needs_exactly_two_decimals():
    with pytest.raises(ValueError):
        parse_amount("455.400,0", decimals=2)


# --- order of prelation ----------------------------------------------------------

def ranking_row(y, rank, tax_id, name, score):
    return [word(str(rank), 100, y), word(tax_id, 130, y), word(name, 230, y), word(score, 480, y)]


def test_ranking_lots_come_from_the_label_and_continue_across_pages():
    page1 = (ranking_row(100, 1, "A11111111", "ALFA", "100,00") + [word("1", 40, 100)]
             + ranking_row(113, 1, "B22222222", "BETA", "100,00") + [word("2", 40, 113)]
             + ranking_row(126, 2, "A11111111", "ALFA", "40,00"))
    page2 = ranking_row(100, 3, "C33333333", "GAMMA", "30,00")
    rows = parse_ranking([(10, page1), (11, page2)])
    assert [(r.lot, r.ranking, r.tax_id) for r in rows] == [
        ("1", 1, "A11111111"), ("2", 1, "B22222222"), ("2", 2, "A11111111"), ("2", 3, "C33333333")]


# --- offers table ----------------------------------------------------------------

BOUNDS = [0, 30, 60, 100, 200, 240, 280, 320, 380, 410, 440, 470]


def cell(text, column, top):
    return word(text, BOUNDS[column] + 3, top, BOUNDS[column + 1] - 3)


def test_offers_table_reads_ocr_columns_by_cell_and_the_rest_from_the_text_layer():
    vertical = [{"x0": x, "x1": x, "top": 0, "bottom": 200} for x in BOUNDS]
    horizontal = [{"x0": 0, "x1": 470, "top": 20, "bottom": 20}, {"x0": 200, "x1": 470, "top": 40, "bottom": 40},
                  {"x0": 0, "x1": 470, "top": 60, "bottom": 60}]
    words = [cell("5", 0, 25), cell("5.1", 1, 25), cell("5", 0, 45), cell("5.2", 1, 45),
             cell("A28985034", 2, 36), cell("BIOTRONICK", 3, 36), cell("703.615,00", 7, 25),
             cell("38.178,00", 7, 45), cell("3,56", 8, 36), cell("40", 9, 36), cell("43,56", 10, 36)]
    rows = parse_offers_page(words, vertical, horizontal, 5, lambda box: f"ocr{round(box[0])}")
    assert [(r.lot, r.order, r.tax_id, r.total_points) for r in rows] == [
        ("5", "5.1", "A28985034", "43,56"), ("5", "5.2", "A28985034", "43,56")]
    assert rows[0].tender_unit_price == "ocr200" and rows[1].offered_total == "38.178,00"
    with pytest.raises(ValueError):
        parse_offers_page(words, vertical[:2], horizontal, 5, str)


# --- prose and LLM ---------------------------------------------------------------

def test_llm_values_not_written_in_the_text_are_discarded(monkeypatch):
    monkeypatch.setattr(narrative, "chat_json", lambda s, u, schema: {
        "file_number": "AM 1/2025", "subject": "Invented", "contracting_authority": None})
    assert narrative.tender_fields("Acta AM  1/2025") == {
        "file_number": "AM 1/2025", "subject": None, "contracting_authority": None}


def test_abnormal_positions_keep_only_the_numbers_written_in_the_paragraph(monkeypatch):
    paragraph = "QUINTO. BOSTON SCIENTIFIC S.A., (Lotes 1.1, 8.4), presunción de baja temeraria."
    monkeypatch.setattr(narrative, "chat_json", lambda s, u, schema: {"findings": [
        {"bidder_name": "BOSTON SCIENTIFIC S.A.", "positions": ["Lotes 1.1", "8.4", "7.7"]}]})
    assert narrative.abnormal_findings(paragraph)[0]["positions"] == ["1.1", "8.4"]


def test_meeting_date_with_a_label_wrapped_over_lines():
    assert str(narrative.meeting_date("Día y hora de la\n23 de julio de 2026 a las 9:00\nreunión:")) == "2026-07-23"


# --- offers ----------------------------------------------------------------------

def offer_row(order, **kwargs):
    values = dict(page=3, lot=order.split(".")[0], order=order, tax_id="A1", bidder="ALFA",
                  tender_unit_price="10,00 €", tender_total="100,00 €", offered_unit_price="9,50 €",
                  offered_total="95,00", price_points="5,00", quality_points="40", total_points="45,00")
    return OfferRow(**{**values, **kwargs})


def test_offer_gets_exact_decimals_and_its_ranking():
    issues = []
    [offer] = extractor._build_offers([offer_row("1.1")], [RankingRow(10, 1, "A1", "ALFA", lot="1")], issues)
    offer_ok = (offer.offered_unit_price, offer.ranking, offer.proposed_awardee) == (Decimal("9.50"), 1, True)
    assert offer_ok and not issues


def test_partly_read_figures_stay_none_and_become_issues():
    issues = []
    [offer] = extractor._build_offers([offer_row("1.1", offered_total="124.950,")], [], issues)
    assert offer.offered_total is None
    assert ("FIGURE_UNREADABLE", "offered_total") in {(i.code, i.field) for i in issues}


def test_bidder_cell_split_by_a_page_break_is_inherited_and_reported():
    first = offer_row("10.2", tax_id="B1", bidder="BETA")
    second = offer_row("10.3", tax_id=None, bidder=None, price_points=None, quality_points=None, total_points=None)
    issues = []
    offers = extractor._build_offers([first, second], [], issues)
    assert [o.bidder.tax_id for o in offers] == ["B1", "B1"] and "BIDDER_INHERITED" in {i.code for i in issues}


def test_llm_down_gives_one_clear_issue_and_the_run_goes_on(monkeypatch):
    def down(system, user, schema):
        raise narrative.LLMError("Ollama request failed")
    monkeypatch.setattr(narrative, "chat_json", down)
    issues = []
    tender, reachable = extractor._read_tender("Día y hora de la reunión: 23 de julio de 2026", issues)
    assert tender is None and not reachable and len([i for i in issues if i.code == "LLM_UNAVAILABLE"]) == 1
