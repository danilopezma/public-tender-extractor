"""Shared field types.

Amounts and scores are Decimal and are never built from floats, so a figure read
from the document cannot silently pick up binary rounding error. Lot and order
identifiers are strings: "1.10" and "1.1" are different orders.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field, StringConstraints


def _reject_float(value):
    if isinstance(value, float):
        raise ValueError("floats are not accepted, pass a str or Decimal")
    return value


# Non-negative Decimal, accepted from str, int or Decimal (not float).
Amount = Annotated[Decimal, BeforeValidator(_reject_float), Field(ge=0, allow_inf_nan=False)]

# Identifier kept exactly as written in the document (only surrounding whitespace is dropped).
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
