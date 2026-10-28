from typing import Optional

from tender_extractor.models.base import SchemaModel
from tender_extractor.models.scalars import Identifier


class Bidder(SchemaModel):
    """Licitador. The tax id (NIF) may be missing or censored in public documents."""

    name: Identifier
    tax_id: Optional[Identifier] = None
