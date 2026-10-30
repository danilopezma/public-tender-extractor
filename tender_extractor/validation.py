"""Validation: coherence checks on the extracted data.

Problems are only reported as issues, never corrected: the extracted value stays as read.
"""

from collections import defaultdict
from typing import List, Optional

from tender_extractor.extraction.tables import RankingRow, parse_amount
from tender_extractor.models import Issue, Offer


def validate(offers: List[Offer], ranking: List[RankingRow]) -> List[Issue]:
    """Check that the extracted offers are coherent with each other and with the order of prelation.

    Checks:
        SCORE_SUM: price points + qualitative points = total points.
        OFFER_ABOVE_TENDER: the offered price is not above the tender price.
        QUANTITY_NOT_INTEGER / TOTAL_MISMATCH: the quantity (tender total / tender unit price)
            is a whole number and the offered total is the offered unit price times it.
        TENDER_PRICE_INCONSISTENT: every bidder has the same tender price for an order.
        RANKING_VS_SCORE: in a lot, a better rank never has fewer points.
        RANKING_WITHOUT_OFFER / SCORE_MISMATCH: Annex 2 (prelation) agrees with Annex 1
            (offers) on who bid and on the total score.

    Args:
        offers: Offers extracted from Annex 1.
        ranking: Rows of the order of prelation (Annex 2), with their lot.

    Returns:
        One issue per problem found; empty if everything is coherent.
    """

    def _issue(code, message, offer=None, field=None, lot=None, bidder=None):
        """Build an issue, taking lot, order and bidder from the offer if given."""
        return Issue(code=code, message=message, field=field,
                     lot=offer.lot if offer else lot,
                     order=offer.order if offer else None,
                     bidder=offer.bidder.tax_id if offer else bidder)

    issues: List[Issue] = []

    # 1. Each offer: scores add up, prices and totals are coherent ------------
    for o in offers:
        if None not in (o.price_points, o.quality_points, o.total_points) \
                and o.price_points + o.quality_points != o.total_points:
            issues.append(_issue("SCORE_SUM", f"{o.price_points} + {o.quality_points} is not "
                                 f"{o.total_points}", o, "total_points"))
        for name in ("offered_unit_price", "offered_total"):
            offered, tender = getattr(o, name), getattr(o, name.replace("offered", "tender"))
            if None not in (offered, tender) and offered > tender:
                issues.append(_issue("OFFER_ABOVE_TENDER", f"{name} {offered} is above the tender "
                                     f"price {tender}", o, name))
        if o.tender_unit_price and o.tender_total is not None:
            quantity = o.tender_total / o.tender_unit_price
            if quantity != quantity.to_integral_value():
                issues.append(_issue("QUANTITY_NOT_INTEGER", f"{o.tender_total} / "
                                     f"{o.tender_unit_price} = {quantity}", o, "tender_total"))
            elif None not in (o.offered_unit_price, o.offered_total) \
                    and o.offered_unit_price * quantity != o.offered_total:
                issues.append(_issue("TOTAL_MISMATCH", f"{o.offered_unit_price} x {quantity:.0f} = "
                                     f"{o.offered_unit_price * quantity}, the document says "
                                     f"{o.offered_total}", o, "offered_total"))

    # 2. Same lot and order: every bidder has the same tender price -----------
    by_order = defaultdict(list)
    for o in offers:
        by_order[(o.lot, o.order)].append(o)
    for (lot, order), group in by_order.items():
        for name in ("tender_unit_price", "tender_total"):
            values = {getattr(o, name) for o in group if getattr(o, name) is not None}
            if len(values) > 1:
                issues.append(Issue(code="TENDER_PRICE_INCONSISTENT", lot=lot, order=order, field=name,
                                    message=f"bidders have different {name}: "
                                            f"{', '.join(str(v) for v in sorted(values))}"))

    # 3. Each lot: a better rank never has fewer points -----------------------
    by_lot = defaultdict(dict)  # lot -> tax id -> offer
    for o in offers:
        if o.ranking is not None and o.total_points is not None:
            by_lot[o.lot].setdefault(o.bidder.tax_id, o)
    for lot, bidders in by_lot.items():
        ordered = sorted(bidders.values(), key=lambda o: o.ranking)
        for better, worse in zip(ordered, ordered[1:]):
            if better.total_points < worse.total_points:
                issues.append(_issue("RANKING_VS_SCORE", f"rank {better.ranking} has "
                                     f"{better.total_points} points, fewer than rank "
                                     f"{worse.ranking} with {worse.total_points}", better, "ranking"))

    # 4. Annex 2 (prelation) against Annex 1 (offers) -------------------------
    totals = {(o.lot, o.bidder.tax_id): o.total_points for o in offers}
    for r in ranking:
        if (r.lot, r.tax_id) not in totals:
            issues.append(_issue("RANKING_WITHOUT_OFFER", f"{r.name} is ranked in Annex 2 but has "
                                 "no row in the offers table", lot=r.lot, bidder=r.tax_id))
            continue
        try:
            score: Optional[object] = parse_amount(r.total_points or "")
        except ValueError:
            issues.append(_issue("FIGURE_UNREADABLE", f"Annex 2 score is {r.total_points!r}",
                                 field="total_points", lot=r.lot, bidder=r.tax_id))
            continue
        if totals[(r.lot, r.tax_id)] not in (None, score):
            issues.append(_issue("SCORE_MISMATCH", f"Annex 1 says {totals[(r.lot, r.tax_id)]}, "
                                 f"Annex 2 says {score}", field="total_points",
                                 lot=r.lot, bidder=r.tax_id))
    return issues
