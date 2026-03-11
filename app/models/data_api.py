"""Pydantic schemas for Generic Data API."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime


# ============================================================================
# Request Schemas
# ============================================================================

class QueryFilter(BaseModel):
    """Filter condition for querying data."""
    
    field: str = Field(..., description="Field name to filter on")
    operator: str = Field(..., description="Comparison operator (eq, ne, gt, lt, gte, lte, like, in, between, is_null)")
    value: Any = Field(None, description="Value to compare against")
    
    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v):
        """Validate operator is one of the allowed values."""
        allowed = ["eq", "ne", "gt", "lt", "gte", "lte", "like", "in", "between", "is_null", "is_not_null"]
        if v not in allowed:
            raise ValueError(f"Invalid operator: {v}. Must be one of: {', '.join(allowed)}")
        return v


class CreateRecordRequest(BaseModel):
    """Request to create a new record."""
    
    object_name: str = Field(..., description="Object name (e.g., 'employee', 'customer')")
    data: Dict[str, Any] = Field(..., description="Record data as key-value pairs")
    
    class Config:
        json_schema_extra = {
            "example": {
                "object_name": "employee",
                "data": {
                    "name": "John Doe",
                    "email": "john@example.com",
                    "department": "Engineering"
                }
            }
        }


class UpdateRecordRequest(BaseModel):
    """Request to update an existing record."""
    
    data: Dict[str, Any] = Field(..., description="Fields to update")
    
    class Config:
        json_schema_extra = {
            "example": {
                "data": {
                    "name": "Jane Doe",
                    "email": "jane@example.com"
                }
            }
        }


class QueryRecordsRequest(BaseModel):
    """Request to query records with filtering, sorting, and pagination."""
    
    object_name: str = Field(..., description="Object name to query")
    filters: Optional[List[QueryFilter]] = Field(None, description="Filter conditions")
    order_by: Optional[List[Dict[str, str]]] = Field(
        None,
        description="Sort order. Each item has 'field' and 'direction' (ASC/DESC)"
    )
    limit: int = Field(100, ge=1, le=1000, description="Maximum records to return")
    offset: int = Field(0, ge=0, description="Number of records to skip")
    
    class Config:
        json_schema_extra = {
            "example": {
                "object_name": "employee",
                "filters": [
                    {"field": "department", "operator": "eq", "value": "Engineering"},
                    {"field": "name", "operator": "like", "value": "%John%"}
                ],
                "order_by": [{"field": "name", "direction": "ASC"}],
                "limit": 50,
                "offset": 0
            }
        }


class BulkCreateRequest(BaseModel):
    """Request to create multiple records."""
    
    object_name: str = Field(..., description="Object name")
    records: List[Dict[str, Any]] = Field(..., description="List of records to create")
    
    @field_validator("records")
    @classmethod
    def validate_records_count(cls, v):
        """Validate records count is within limits."""
        if len(v) > 1000:
            raise ValueError("Cannot create more than 1000 records at once")
        if len(v) == 0:
            raise ValueError("Must provide at least one record")
        return v


class BulkUpdateRequest(BaseModel):
    """Request to update multiple records."""
    
    object_name: str = Field(..., description="Object name")
    filters: List[QueryFilter] = Field(..., description="Filter to identify records to update")
    data: Dict[str, Any] = Field(..., description="Fields to update")


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple records."""
    
    object_name: str = Field(..., description="Object name")
    filters: List[QueryFilter] = Field(..., description="Filter to identify records to delete")


class AggregationField(BaseModel):
    """Aggregation field specification."""
    
    field: str = Field(..., description="Field name to aggregate")
    function: str = Field(..., description="Aggregation function (count, sum, avg, min, max)")
    alias: Optional[str] = Field(None, description="Alias for the result")
    
    @field_validator("function")
    @classmethod
    def validate_function(cls, v):
        """Validate aggregation function."""
        allowed = ["count", "sum", "avg", "min", "max", "count_distinct"]
        if v.lower() not in allowed:
            raise ValueError(f"Invalid function: {v}. Must be one of: {', '.join(allowed)}")
        return v.lower()


class AggregateQueryRequest(BaseModel):
    """Request to query with aggregations."""
    
    object_name: str = Field(..., description="Object name to query")
    aggregations: List[AggregationField] = Field(..., description="Aggregation fields")
    group_by: Optional[List[str]] = Field(None, description="Fields to group by")
    filters: Optional[List[QueryFilter]] = Field(None, description="Filter conditions")
    having: Optional[List[QueryFilter]] = Field(None, description="HAVING conditions for aggregated results")
    order_by: Optional[List[Dict[str, str]]] = Field(None, description="Sort order")
    limit: int = Field(1000, ge=1, le=10000, description="Maximum records to return")
    offset: int = Field(0, ge=0, description="Number of records to skip")


class ExportRequest(BaseModel):
    """Request to export data."""
    
    object_name: str = Field(..., description="Object name to export")
    format: str = Field(..., description="Export format (csv, json, excel)")
    filters: Optional[List[QueryFilter]] = Field(None, description="Filter conditions")
    fields: Optional[List[str]] = Field(None, description="Specific fields to export (all if not specified)")
    order_by: Optional[List[Dict[str, str]]] = Field(None, description="Sort order")
    limit: Optional[int] = Field(None, ge=1, le=100000, description="Maximum records to export")
    
    @field_validator("format")
    @classmethod
    def validate_format(cls, v):
        """Validate export format."""
        allowed = ["csv", "json", "excel"]
        if v.lower() not in allowed:
            raise ValueError(f"Invalid format: {v}. Must be one of: {', '.join(allowed)}")
        return v.lower()


class ImportRequest(BaseModel):
    """Request to import data."""
    
    object_name: str = Field(..., description="Object name to import into")
    format: str = Field(..., description="Import format (csv, json)")
    data: str = Field(..., description="Base64 encoded file content")
    mode: str = Field("insert", description="Import mode (insert, upsert, update)")
    upsert_key: Optional[List[str]] = Field(None, description="Fields to use for upsert matching")
    validate_only: bool = Field(False, description="Only validate without importing")
    
    @field_validator("format")
    @classmethod
    def validate_format(cls, v):
        """Validate import format."""
        allowed = ["csv", "json"]
        if v.lower() not in allowed:
            raise ValueError(f"Invalid format: {v}. Must be one of: {', '.join(allowed)}")
        return v.lower()
    
    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        """Validate import mode."""
        allowed = ["insert", "upsert", "update"]
        if v.lower() not in allowed:
            raise ValueError(f"Invalid mode: {v}. Must be one of: {', '.join(allowed)}")
        return v.lower()


# ============================================================================
# Response Schemas
# ============================================================================

class RecordResponse(BaseModel):
    """Single record response."""
    
    id: UUID = Field(..., description="Record ID")
    data: Dict[str, Any] = Field(..., description="Record data")
    created_at: datetime = Field(..., description="Creation timestamp")
    created_by: UUID = Field(..., description="User who created the record")
    modified_at: datetime = Field(..., description="Last modification timestamp")
    modified_by: UUID = Field(..., description="User who last modified the record")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "data": {
                    "name": "John Doe",
                    "email": "john@example.com",
                    "department": "Engineering"
                },
                "created_at": "2024-01-15T10:30:00Z",
                "created_by": "user-uuid-here",
                "modified_at": "2024-01-15T10:30:00Z",
                "modified_by": "user-uuid-here"
            }
        }


class QueryRecordsResponse(BaseModel):
    """Paginated query response."""
    
    records: List[RecordResponse] = Field(..., description="List of records")
    total: int = Field(..., description="Total number of records matching the query")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Offset")
    has_more: bool = Field(..., description="Whether there are more records")
    
    class Config:
        json_schema_extra = {
            "example": {
                "records": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "data": {"name": "John Doe", "email": "john@example.com"},
                        "created_at": "2024-01-15T10:30:00Z",
                        "created_by": "user-uuid",
                        "modified_at": "2024-01-15T10:30:00Z",
                        "modified_by": "user-uuid"
                    }
                ],
                "total": 150,
                "limit": 50,
                "offset": 0,
                "has_more": True
            }
        }


class BulkOperationResponse(BaseModel):
    """Response for bulk operations."""
    
    affected_count: int = Field(..., description="Number of records affected")
    record_ids: Optional[List[UUID]] = Field(None, description="IDs of affected records (for create/update)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "affected_count": 25,
                "record_ids": ["uuid1", "uuid2", "..."]
            }
        }


class AggregateQueryResponse(BaseModel):
    """Response for aggregate queries."""
    
    results: List[Dict[str, Any]] = Field(..., description="Aggregation results")
    total: int = Field(..., description="Total number of result rows")
    
    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {"department": "Engineering", "count": 50, "avg_salary": 125000},
                    {"department": "Sales", "count": 30, "avg_salary": 95000}
                ],
                "total": 2
            }
        }


class ExportResponse(BaseModel):
    """Response for export operations."""
    
    download_url: Optional[str] = Field(None, description="URL to download the export (for async exports)")
    data: Optional[str] = Field(None, description="Base64 encoded export data (for sync exports)")
    format: str = Field(..., description="Export format")
    record_count: int = Field(..., description="Number of records exported")
    size_bytes: int = Field(..., description="Size of export in bytes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "data": "base64encodedcontent...",
                "format": "csv",
                "record_count": 1500,
                "size_bytes": 245678
            }
        }


class ImportValidationError(BaseModel):
    """Validation error for import."""
    
    row: int = Field(..., description="Row number (1-based)")
    field: Optional[str] = Field(None, description="Field name")
    message: str = Field(..., description="Error message")


class ImportResponse(BaseModel):
    """Response for import operations."""
    
    total_rows: int = Field(..., description="Total rows in import file")
    valid_rows: int = Field(..., description="Number of valid rows")
    invalid_rows: int = Field(..., description="Number of invalid rows")
    imported_count: int = Field(..., description="Number of records imported (0 for validate_only)")
    validation_errors: List[ImportValidationError] = Field(default_factory=list, description="Validation errors")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_rows": 1000,
                "valid_rows": 995,
                "invalid_rows": 5,
                "imported_count": 995,
                "validation_errors": [
                    {"row": 15, "field": "email", "message": "Invalid email format"},
                    {"row": 47, "field": "salary", "message": "Must be a number"}
                ]
            }
        }


class ErrorDetail(BaseModel):
    """Error detail."""
    
    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")


class ErrorResponse(BaseModel):
    """Error response."""
    
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[List[ErrorDetail]] = Field(None, description="Additional error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "PermissionDenied",
                "message": "You do not have permission to write to this object",
                "details": [
                    {"field": "salary", "message": "Read-only field", "code": "FIELD_READ_ONLY"}
                ]
            }
        }
