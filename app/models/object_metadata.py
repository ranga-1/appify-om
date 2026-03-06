"""Pydantic models for Object Metadata API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ObjectMetadataCreate(BaseModel):
    """Request model for creating object metadata."""
    
    label: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Display label (alphanumeric + spaces)"
    )
    description: Optional[str] = Field(None, description="Object description")
    used_in_global_search: bool = Field(
        False,
        description="Include in global search"
    )
    enable_audit: bool = Field(False, description="Enable audit trail")
    is_remote_object: bool = Field(
        False,
        description="Is remote/external object"
    )
    fields: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Field definitions (JSONB)"
    )
    
    @field_validator('label')
    @classmethod
    def validate_label(cls, v: str) -> str:
        """Label must have at least one alphanumeric character."""
        if not any(c.isalnum() for c in v):
            raise ValueError(
                "Label must contain at least one alphanumeric character"
            )
        return v.strip()


class ObjectMetadataUpdate(BaseModel):
    """Request model for updating object metadata."""
    
    label: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    used_in_global_search: Optional[bool] = None
    enable_audit: Optional[bool] = None
    is_remote_object: Optional[bool] = None
    fields: Optional[List[Dict[str, Any]]] = None
    
    @field_validator('label')
    @classmethod
    def validate_label(cls, v: Optional[str]) -> Optional[str]:
        """Label must have at least one alphanumeric character."""
        if v is not None:
            if not any(c.isalnum() for c in v):
                raise ValueError(
                    "Label must contain at least one alphanumeric character"
                )
            return v.strip()
        return v


class ObjectMetadataResponse(BaseModel):
    """Response model for object metadata."""
    
    id: UUID
    label: str
    api_name: str
    description: Optional[str]
    used_in_global_search: bool
    enable_audit: bool
    is_remote_object: bool
    fields: List[Dict[str, Any]]
    created_by: UUID
    created_date: datetime
    modified_by: UUID
    modified_date: datetime
    
    class Config:
        from_attributes = True


class ObjectMetadataListResponse(BaseModel):
    """Response model for paginated object metadata list."""
    
    items: List[ObjectMetadataResponse]
    total: int
    skip: int
    limit: int
