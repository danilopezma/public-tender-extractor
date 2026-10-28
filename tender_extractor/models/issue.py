from typing import Optional

from tender_extractor.models.base import SchemaModel
from tender_extractor.models.scalars import Identifier


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
