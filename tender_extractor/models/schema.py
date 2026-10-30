"""Data models of the tender meeting record.

Amounts and scores are Decimal and are never built from floats, so a figure read from
the document cannot silently pick up binary rounding error. Lot and order identifiers
are strings: "1.10" and "1.1" are different orders. Every figure of an offer is
optional: a value that is missing or unreadable stays None and is reported as an issue,
never guessed.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints


def _reject_float(value):
    """Reject floats before conversion, so no figure goes through binary arithmetic.

    Args:
        value: Raw value of an amount field.

    Returns:
        The same value if it is not a float.

    Raises:
        ValueError: The value is a float.
    """
    if isinstance(value, float):
        raise ValueError("floats are not accepted, pass a str or Decimal")
    return value


# Non-negative Decimal, accepted from str, int or Decimal (not float).
Amount = Annotated[Decimal, BeforeValidator(_reject_float), Field(ge=0, allow_inf_nan=False)]

# Identifier kept exactly as written in the document (only surrounding whitespace is dropped).
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SchemaModel(BaseModel):
    """Base for all models: unknown fields are errors, so typos never pass silently."""

    model_config = ConfigDict(extra="forbid")


class Tender(SchemaModel):
    """Expediente: the procurement file the meeting record belong to."""

    file_number: Identifier
    subject: Optional[str] = None
    contracting_authority: Optional[str] = None
    meeting_date: Optional[date] = None


class Bidder(SchemaModel):
    """Licitador. The tax id (NIF) may be missing or censored in public documents."""

    name: Identifier
    tax_id: Optional[Identifier] = None


class Offer(SchemaModel):
    """Oferta: one bidder's offer for one lot (and order/sublot, if the lot has them)."""

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

    ranking: Optional[int] = Field(default=None, ge=1)  # orden de prelación
    proposed_awardee: Optional[bool] = None

    abnormally_low: Optional[bool] = None  # presumed abnormal or reckless low offer
    abnormally_low_positions: List[Identifier] = Field(default_factory=list)  # as written


class Issue(SchemaModel):
    """Incidencia: a problem or inconsistency found while extracting or validating.

    Issues are reported, never fixed: the extracted value stays as read.
    """

    code: Identifier
    message: Identifier
    lot: Optional[Identifier] = None
    order: Optional[Identifier] = None
    bidder: Optional[Identifier] = None
    field: Optional[Identifier] = None
