from decimal import Decimal
from typing import List, Optional

from pydantic import Field

from tender_extractor.models.base import SchemaModel
from tender_extractor.models.bidder import Bidder
from tender_extractor.models.scalars import Amount, Identifier


class Offer(SchemaModel):
    """Oferta: one bidder's offer for one lot (and order/sublot, if the lot has them).

    Every figure is optional: a value that is missing or unreadable stays None
    and is reported as an issue, never guessed.
    """

    lot: Identifier
    order: Optional[Identifier] = None
    bidder: Bidder

    tender_unit_price: Optional[Amount] = None
    offered_unit_price: Optional[Amount] = None
    tender_total: Optional[Amount] = None
    offered_total: Optional[Amount] = None

    price_points: Optional[Amount] = None
    quality_points: Optional[Amount] = None
    total_points: Optional[Amount] = None

    ranking: Optional[int] = Field(default=None, ge=1, description="Orden de prelación")
    proposed_awardee: Optional[bool] = None

    abnormally_low: Optional[bool] = Field(
        default=None, description="Presumed abnormal or reckless low offer"
    )
    abnormally_low_positions: List[Identifier] = Field(
        default_factory=list,
        description="Positions the abnormally-low presumption refers to, as written",
    )

