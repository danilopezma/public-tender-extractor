import pytest
from pydantic import ValidationError

from tender_extractor.models import Bidder, Offer


def offer(**kwargs):
    return Offer(lot="1", bidder=Bidder(name="ACME S.L."), **kwargs)


def test_lot_and_order_stay_strings_as_written():
    assert offer(order="1.10").order == "1.10"
    with pytest.raises(ValidationError):
        offer(order=1.1)


def test_amounts_are_exact_decimals_and_floats_are_rejected():
    assert str(offer(offered_total="12789.50").offered_total) == "12789.50"
    with pytest.raises(ValidationError):
        offer(offered_total=0.1)


def test_negative_and_non_numeric_amounts_are_rejected():
    for value in ("-1", "NaN", "abc"):
        with pytest.raises(ValidationError):
            offer(offered_total=value)


def test_missing_figures_stay_none():
    assert offer().offered_total is None
