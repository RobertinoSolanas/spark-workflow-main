from uuid import UUID

from pydantic import BaseModel


class TypeResponse(BaseModel):
    """Pydantic model for simple type mappings."""

    id: UUID
    name: str

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
