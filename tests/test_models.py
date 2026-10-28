import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tender_extractor.models import Bidder, Issue, Offer, Tender


def offer(**kwargs):
    data = {"lot": "1", "bidder": Bidder(name="ACME S.L.")}
    data.update(kwargs)
    return Offer(**data)


def test_lot_and_order_are_kept_as_strings():
    o = offer(lot="01", order="1.10")
    assert (o.lot, o.order) == ("01", "1.10")


@pytest.mark.parametrize("field", ["lot", "order"])
def test_lot_and_order_reject_numbers(field):
    with pytest.raises(ValidationError):
        offer(**{field: 1})


def test_lot_cannot_be_blank():
    with pytest.raises(ValidationError):
        offer(lot="  ")


def test_amounts_are_exact_decimals_from_strings():
    o = offer(offered_unit_price="12789.50", price_points="45.123456789")
    assert o.offered_unit_price == Decimal("12789.50")
    assert str(o.offered_unit_price) == "12789.50"  # trailing zero preserved
    assert o.price_points == Decimal("45.123456789")


def test_floats_are_rejected():
    with pytest.raises(ValidationError):
        offer(offered_unit_price=0.1)


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "abc"])
def test_invalid_amounts_are_rejected(value):
    with pytest.raises(ValidationError):
        offer(offered_total=value)


def test_missing_figures_stay_none():
    o = offer()
    assert o.offered_unit_price is None and o.total_points is None and o.ranking is None


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        offer(price="1")


def test_ranking_must_be_positive():
    with pytest.raises(ValidationError):
        offer(ranking=0)


def test_issue_requires_code_and_message():
    i = Issue(code="PRICE_ABOVE_TENDER", message="offer exceeds tender price", lot="3")
    assert (i.code, i.lot, i.order) == ("PRICE_ABOVE_TENDER", "3", None)
    with pytest.raises(ValidationError):
        Issue(code="X")
    with pytest.raises(ValidationError):
        Issue(code="X", message="  ")


def test_json_round_trip_keeps_decimals_exact():
    o = offer(order="1.1", offered_unit_price="12789.50", proposed_awardee=True)
    raw = o.model_dump_json()
    assert json.loads(raw)["offered_unit_price"] == "12789.50"
    assert Offer.model_validate_json(raw) == o


def test_tender_parses_meeting_date():
    t = Tender(file_number="AM PA SUM 42/2025", meeting_date="2025-05-20")
    assert t.meeting_date == date(2025, 5, 20)
