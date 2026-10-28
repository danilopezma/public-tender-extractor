from datetime import date
from typing import Optional

from tender_extractor.models.base import SchemaModel
from tender_extractor.models.scalars import Identifier


class Tender(SchemaModel):
    """Expediente: the procurement file the minutes belong to."""

    file_number: Identifier
    subject: Optional[str] = None
    contracting_authority: Optional[str] = None
    meeting_date: Optional[date] = None
