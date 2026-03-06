"""Datatype Mapping models for Object Modeler."""

from typing import Any, Dict
from pydantic import BaseModel


class DatatypeMappingResponse(BaseModel):
    """Response model for datatype mapping."""
    
    db_datatype: str  # PostgreSQL datatype (VARCHAR, INTEGER, etc.)
    om_datatype: str  # Object Modeler datatype (Text, Number, etc.)
    properties: Dict[str, Any]  # Property schema for UI rendering
    
    class Config:
        from_attributes = True
