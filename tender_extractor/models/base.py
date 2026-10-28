from pydantic import BaseModel, ConfigDict


class SchemaModel(BaseModel):
    """Base for all models: unknown fields are errors, so typos never pass silently."""

    model_config = ConfigDict(extra="forbid")
