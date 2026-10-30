from tender_extractor.extraction.tables import RankingRow
from tender_extractor.models import Bidder, Offer
from tender_extractor.validation import validate


def offer(tax_id="A1", lot="1", order="1.1", **kwargs):
    values = dict(tender_unit_price="10.00", tender_total="100.00", offered_unit_price="9.00",
                  offered_total="90.00", price_points="5.00", quality_points="40.00",
                  total_points="45.00", ranking=1)
    return Offer(lot=lot, order=order, bidder=Bidder(name=tax_id, tax_id=tax_id), **{**values, **kwargs})


def codes(offers, ranking=()):
    return [i.code for i in validate(offers, list(ranking))]


def test_coherent_data_has_no_issues():
    assert codes([offer()], [RankingRow(10, 1, "A1", "A1", "45,00", lot="1")]) == []


def test_scores_that_do_not_add_up_are_reported():
    assert codes([offer(total_points="46.00")]) == ["SCORE_SUM"]


def test_offer_above_the_tender_price_is_reported():
    assert codes([offer(offered_unit_price="11.00", offered_total="110.00")]) == [
        "OFFER_ABOVE_TENDER", "OFFER_ABOVE_TENDER"]


def test_offered_total_must_be_unit_price_times_quantity():
    [issue] = validate([offer(offered_total="85.00")], [])
    assert issue.code == "TOTAL_MISMATCH" and "9.00 x 10 = 90.00" in issue.message


def test_quantity_must_be_a_whole_number():
    assert codes([offer(tender_total="105.00")]) == ["QUANTITY_NOT_INTEGER"]


def test_bidders_must_share_the_tender_price_of_an_order():
    assert codes([offer("A1"), offer("B2", tender_unit_price="12.00", tender_total="120.00", ranking=2,
                                     total_points="40.00", quality_points="35.00")]
                 ) == ["TENDER_PRICE_INCONSISTENT"] * 2


def test_a_better_rank_cannot_have_fewer_points():
    assert codes([offer("A1", ranking=1, total_points="40.00", quality_points="35.00"),
                  offer("B2", ranking=2)]) == ["RANKING_VS_SCORE"]


def test_annex_2_must_agree_with_annex_1():
    ranking = [RankingRow(10, 1, "A1", "A1", "44,00", lot="1"), RankingRow(10, 2, "Z9", "ZETA", "1,00", lot="1")]
    assert codes([offer()], ranking) == ["SCORE_MISMATCH", "RANKING_WITHOUT_OFFER"]


def test_missing_figures_are_skipped_not_reported_here():
    assert codes([offer(offered_total=None, total_points=None)]) == []
