"""Generic Data API endpoints with permission enforcement."""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
import logging
import io
import csv
import json
import base64
from datetime import datetime

from app.models.data_api import (
    CreateRecordRequest,
    UpdateRecordRequest,
    QueryRecordsRequest,
    BulkCreateRequest,
    BulkUpdateRequest,
    BulkDeleteRequest,
    AggregateQueryRequest,
    ExportRequest,
    ImportRequest,
    RecordResponse,
    QueryRecordsResponse,
    BulkOperationResponse,
    AggregateQueryResponse,
    ExportResponse,
    ImportResponse,
    ErrorResponse
)
from app.db.connection import get_tenant_db
from app.services.permissions.permission_service import get_permission_service
from app.services.permissions.permission_checker import PermissionChecker, Scope, FieldAccess
from app.services.permissions.secure_query_builder import SecureQueryBuilder, QueryFilter as SQLQueryFilter
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


# ============================================================================
# Dependency: Get current user from request
# ============================================================================

def get_current_user(x_user_id: str = Header(..., alias="X-User-ID")) -> UUID:
    """
    Extract user ID from request header.
    
    In production, this would validate JWT token and extract user_id.
    For now, we accept X-User-ID header from the gateway.
    """
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format"
        )


def get_tenant_schema(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """
    Extract tenant schema name from request header.
    
    This header is set by the API gateway after validating the tenant.
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant ID"
        )
    return x_tenant_id


# ============================================================================
# Helper Functions
# ============================================================================

async def get_object_id_and_metadata(
    db: Session,
    schema_name: str,
    object_name: str
) -> tuple[UUID, dict]:
    """
    Get object metadata from sys_object_metadata.
    
    Returns:
        Tuple of (object_id, metadata_dict)
    """
    query = text(f"""
        SELECT id, object_prefix, table_name, fields
        FROM {schema_name}.sys_object_metadata
        WHERE object_name = :object_name
        AND is_active = true
    """)
    
    result = db.execute(query, {"object_name": object_name}).fetchone()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Object '{object_name}' not found"
        )
    
    metadata = {
        "object_id": result.id,
        "object_prefix": result.object_prefix,
        "table_name": result.table_name,
        "fields": result.fields or {}
    }
    
    return result.id, metadata


async def check_permission_and_build_query(
    db: Session,
    schema_name: str,
    user_id: UUID,
    object_id: UUID,
    object_metadata: dict,
    action: str
) -> tuple[PermissionChecker, SecureQueryBuilder]:
    """
    Check permissions and create secure query builder.
    
    Args:
        db: Database session
        schema_name: Tenant schema name
        user_id: Current user ID
        object_id: Object ID
        object_metadata: Object metadata dict
        action: Action to check (read, create, update, delete)
        
    Returns:
        Tuple of (permission_checker, query_builder)
    """
    # Get permission service
    perm_service = get_permission_service(db)
    
    # Get all field names from metadata
    all_fields = list(object_metadata["fields"].keys()) if object_metadata["fields"] else []
    
    # Get user permissions
    permission_set = perm_service.get_user_permissions(user_id, object_id, all_fields)
    
    # Check if user has permission for this action
    required_perm = f"data:{action}:*"
    if not PermissionChecker.has_permission(permission_set.permissions, required_perm):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to {action} records in this object"
        )
    
    # Get data scope
    scope = PermissionChecker.get_data_scope(permission_set.permissions, action)
    
    # Create secure query builder
    query_builder = SecureQueryBuilder(
        schema_name=schema_name,
        table_name=object_metadata["table_name"],
        user_id=user_id,
        scope=scope,
        field_access=permission_set.field_permissions
    )
    
    return PermissionChecker, query_builder


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.post(
    "/records",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new record",
    responses={
        201: {"description": "Record created successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Object not found"}
    }
)
async def create_record(
    request: CreateRecordRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Create a new record in the specified object.
    
    Permissions required:
    - data:create:* or data:create:{object_name}
    - field:write:* for each field being set
    
    The record will be created with:
    - created_by = current user
    - modified_by = current user
    - created_at = current timestamp
    - modified_at = current timestamp
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, request.object_name
        )
        
        # Check permissions and get query builder
        _, query_builder = await check_permission_and_build_query(
            db, tenant_schema, user_id, object_id, metadata, "create"
        )
        
        # Build INSERT query
        sql, params = query_builder.build_insert(request.data)
        
        # Execute query
        result = db.execute(text(sql), params)
        db.commit()
        
        # Get the created record ID
        record_id = result.fetchone()[0]
        
        # Fetch the created record
        select_sql, select_params = query_builder.build_select(
            filters=[SQLQueryFilter("id", "eq", record_id)]
        )
        
        record = db.execute(text(select_sql), select_params).fetchone()
        
        return RecordResponse(
            id=record.id,
            data=dict(record._mapping),
            created_at=record.created_at,
            created_by=record.created_by,
            modified_at=record.modified_at,
            modified_by=record.modified_by
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating record: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create record: {str(e)}"
        )


@router.get(
    "/records/{record_id}",
    response_model=RecordResponse,
    summary="Get a record by ID",
    responses={
        200: {"description": "Record retrieved successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Record not found"}
    }
)
async def get_record(
    record_id: UUID,
    object_name: str,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Get a single record by ID.
    
    Permissions required:
    - data:read:* or data:read:{object_name}
    - Appropriate field-level permissions for each field
    
    Fields will be masked or hidden based on field permissions:
    - WRITE/READ: Field value returned
    - MASK: Returns '***MASKED***'
    - HIDE: Field not included in response
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, object_name
        )
        
        # Check permissions and get query builder
        _, query_builder = await check_permission_and_build_query(
            db, tenant_schema, user_id, object_id, metadata, "read"
        )
        
        # Build SELECT query
        sql, params = query_builder.build_select(
            filters=[SQLQueryFilter("id", "eq", str(record_id))]
        )
        
        # Execute query
        result = db.execute(text(sql), params).fetchone()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Record {record_id} not found or you don't have permission to view it"
            )
        
        return RecordResponse(
            id=result.id,
            data=dict(result._mapping),
            created_at=result.created_at,
            created_by=result.created_by,
            modified_at=result.modified_at,
            modified_by=result.modified_by
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving record: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve record: {str(e)}"
        )


@router.put(
    "/records/{record_id}",
    response_model=RecordResponse,
    summary="Update a record by ID",
    responses={
        200: {"description": "Record updated successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Record not found"}
    }
)
async def update_record(
    record_id: UUID,
    object_name: str,
    request: UpdateRecordRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Update a record by ID.
    
    Permissions required:
    - data:update:* or data:update:{object_name}
    - field:write:* for each field being updated
    - Appropriate data scope to access the record
    
    The record will be updated with:
    - modified_by = current user
    - modified_at = current timestamp
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, object_name
        )
        
        # Check permissions and get query builder
        _, query_builder = await check_permission_and_build_query(
            db, tenant_schema, user_id, object_id, metadata, "update"
        )
        
        # Build UPDATE query
        sql, params = query_builder.build_update(
            request.data,
            filters=[SQLQueryFilter("id", "eq", str(record_id))]
        )
        
        # Execute query
        result = db.execute(text(sql), params)
        db.commit()
        
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Record {record_id} not found or you don't have permission to update it"
            )
        
        # Fetch the updated record
        select_sql, select_params = query_builder.build_select(
            filters=[SQLQueryFilter("id", "eq", str(record_id))]
        )
        
        record = db.execute(text(select_sql), select_params).fetchone()
        
        return RecordResponse(
            id=record.id,
            data=dict(record._mapping),
            created_at=record.created_at,
            created_by=record.created_by,
            modified_at=record.modified_at,
            modified_by=record.modified_by
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating record: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update record: {str(e)}"
        )


@router.delete(
    "/records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a record by ID",
    responses={
        204: {"description": "Record deleted successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Record not found"}
    }
)
async def delete_record(
    record_id: UUID,
    object_name: str,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Delete a record by ID.
    
    Permissions required:
    - data:delete:* or data:delete:{object_name}
    - Appropriate data scope to access the record
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, object_name
        )
        
        # Check permissions and get query builder
        _, query_builder = await check_permission_and_build_query(
            db, tenant_schema, user_id, object_id, metadata, "delete"
        )
        
        # Build DELETE query
        sql, params = query_builder.build_delete(
            filters=[SQLQueryFilter("id", "eq", str(record_id))]
        )
        
        # Execute query
        result = db.execute(text(sql), params)
        db.commit()
        
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Record {record_id} not found or you don't have permission to delete it"
            )
        
        return None  # 204 No Content
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting record: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete record: {str(e)}"
        )


@router.post(
    "/query",
    response_model=QueryRecordsResponse,
    summary="Query records with filtering and pagination",
    responses={
        200: {"description": "Query executed successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"}
    }
)
async def query_records(
    request: QueryRecordsRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Query records with filtering, sorting, and pagination.
    
    Permissions required:
    - data:read:* or data:read:{object_name}
    - Appropriate field-level permissions for filtering and sorting
    
    Features:
    - Filter by multiple conditions (AND logic)
    - Sort by multiple fields
    - Pagination with limit/offset
    - Automatic scope-based filtering
    - Field masking/hiding based on permissions
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, request.object_name
        )
        
        # Check permissions and get query builder
        _, query_builder = await check_permission_and_build_query(
            db, tenant_schema, user_id, object_id, metadata, "read"
        )
        
        # Convert filters to SQL filters
        sql_filters = []
        if request.filters:
            for f in request.filters:
                sql_filters.append(SQLQueryFilter(f.field, f.operator, f.value))
        
        # Convert order_by
        order_by = None
        if request.order_by:
            order_by = [(item["field"], item["direction"]) for item in request.order_by]
        
        # Build count query
        count_sql, count_params = query_builder.build_count(filters=sql_filters)
        total_result = db.execute(text(count_sql), count_params).fetchone()
        total = total_result.count if total_result else 0
        
        # Build select query
        select_sql, select_params = query_builder.build_select(
            filters=sql_filters,
            order_by=order_by,
            limit=request.limit,
            offset=request.offset
        )
        
        # Execute query
        results = db.execute(text(select_sql), select_params).fetchall()
        
        # Convert to response
        records = []
        for row in results:
            records.append(RecordResponse(
                id=row.id,
                data=dict(row._mapping),
                created_at=row.created_at,
                created_by=row.created_by,
                modified_at=row.modified_at,
                modified_by=row.modified_by
            ))
        
        return QueryRecordsResponse(
            records=records,
            total=total,
            limit=request.limit,
            offset=request.offset,
            has_more=(request.offset + request.limit) < total
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error querying records: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query records: {str(e)}"
        )


# ============================================================================
# Bulk Operations Endpoints
# ============================================================================

@router.post(
    "/bulk/create",
    response_model=BulkOperationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk create records",
    responses={
        201: {"description": "Records created successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"}
    }
)
async def bulk_create_records(
    request: BulkCreateRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Create multiple records at once.
    
    Permissions required:
    - bulk:create:* or bulk:create:{object_name}
    - field:write:* for each field being set
    
    Maximum 1000 records per request.
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, request.object_name
        )
        
        # Check permissions for bulk operations
        perm_service = get_permission_service(db)
        all_fields = list(metadata["fields"].keys()) if metadata["fields"] else []
        permission_set = perm_service.get_user_permissions(user_id, object_id, all_fields)
        
        # Check bulk create permission
        required_perm = f"bulk:create:*"
        if not PermissionChecker.has_permission(permission_set.permissions, required_perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to bulk create records"
            )
        
        # Get data scope
        scope = PermissionChecker.get_data_scope(permission_set.permissions, "create")
        
        # Create secure query builder
        query_builder = SecureQueryBuilder(
            schema_name=tenant_schema,
            table_name=metadata["table_name"],
            user_id=user_id,
            scope=scope,
            field_access=permission_set.field_permissions
        )
        
        # Insert records
        record_ids = []
        for record_data in request.records:
            sql, params = query_builder.build_insert(record_data)
            result = db.execute(text(sql), params)
            record_id = result.fetchone()[0]
            record_ids.append(record_id)
        
        db.commit()
        
        return BulkOperationResponse(
            affected_count=len(record_ids),
            record_ids=record_ids
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error bulk creating records: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk create records: {str(e)}"
        )


@router.post(
    "/bulk/update",
    response_model=BulkOperationResponse,
    summary="Bulk update records",
    responses={
        200: {"description": "Records updated successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"}
    }
)
async def bulk_update_records(
    request: BulkUpdateRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Update multiple records matching filters.
    
    Permissions required:
    - bulk:update:* or bulk:update:{object_name}
    - field:write:* for each field being updated
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, request.object_name
        )
        
        # Check permissions
        perm_service = get_permission_service(db)
        all_fields = list(metadata["fields"].keys()) if metadata["fields"] else []
        permission_set = perm_service.get_user_permissions(user_id, object_id, all_fields)
        
        required_perm = f"bulk:update:*"
        if not PermissionChecker.has_permission(permission_set.permissions, required_perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to bulk update records"
            )
        
        scope = PermissionChecker.get_data_scope(permission_set.permissions, "update")
        
        query_builder = SecureQueryBuilder(
            schema_name=tenant_schema,
            table_name=metadata["table_name"],
            user_id=user_id,
            scope=scope,
            field_access=permission_set.field_permissions
        )
        
        # Convert filters
        sql_filters = [SQLQueryFilter(f.field, f.operator, f.value) for f in request.filters]
        
        # Build and execute update
        sql, params = query_builder.build_update(request.data, filters=sql_filters)
        result = db.execute(text(sql), params)
        db.commit()
        
        return BulkOperationResponse(
            affected_count=result.rowcount,
            record_ids=None
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error bulk updating records: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk update records: {str(e)}"
        )


@router.post(
    "/bulk/delete",
    response_model=BulkOperationResponse,
    summary="Bulk delete records",
    responses={
        200: {"description": "Records deleted successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"}
    }
)
async def bulk_delete_records(
    request: BulkDeleteRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Delete multiple records matching filters.
    
    Permissions required:
    - bulk:delete:* or bulk:delete:{object_name}
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, request.object_name
        )
        
        # Check permissions
        perm_service = get_permission_service(db)
        all_fields = list(metadata["fields"].keys()) if metadata["fields"] else []
        permission_set = perm_service.get_user_permissions(user_id, object_id, all_fields)
        
        required_perm = f"bulk:delete:*"
        if not PermissionChecker.has_permission(permission_set.permissions, required_perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to bulk delete records"
            )
        
        scope = PermissionChecker.get_data_scope(permission_set.permissions, "delete")
        
        query_builder = SecureQueryBuilder(
            schema_name=tenant_schema,
            table_name=metadata["table_name"],
            user_id=user_id,
            scope=scope,
            field_access=permission_set.field_permissions
        )
        
        # Convert filters
        sql_filters = [SQLQueryFilter(f.field, f.operator, f.value) for f in request.filters]
        
        # Build and execute delete
        sql, params = query_builder.build_delete(filters=sql_filters)
        result = db.execute(text(sql), params)
        db.commit()
        
        return BulkOperationResponse(
            affected_count=result.rowcount,
            record_ids=None
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error bulk deleting records: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk delete records: {str(e)}"
        )


# ============================================================================
# Advanced Query Endpoints
# ============================================================================

@router.post(
    "/aggregate",
    response_model=AggregateQueryResponse,
    summary="Query with aggregations and grouping",
    responses={
        200: {"description": "Aggregation query executed successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"}
    }
)
async def aggregate_query(
    request: AggregateQueryRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Execute aggregation query with GROUP BY and HAVING.
    
    Permissions required:
    - data:read:* or data:read:{object_name}
    - query:aggregate:* for advanced queries
    
    Supports:
    - COUNT, SUM, AVG, MIN, MAX, COUNT(DISTINCT)
    - GROUP BY multiple fields
    - HAVING filters on aggregated results
    - ORDER BY, LIMIT, OFFSET
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, request.object_name
        )
        
        # Check permissions
        perm_service = get_permission_service(db)
        all_fields = list(metadata["fields"].keys()) if metadata["fields"] else []
        permission_set = perm_service.get_user_permissions(user_id, object_id, all_fields)
        
        # Check basic read permission
        if not PermissionChecker.has_permission(permission_set.permissions, "data:read:*"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to read records"
            )
        
        # Check aggregation permission
        if not PermissionChecker.has_permission(permission_set.permissions, "query:aggregate:*"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to execute aggregate queries"
            )
        
        scope = PermissionChecker.get_data_scope(permission_set.permissions, "read")
        
        query_builder = SecureQueryBuilder(
            schema_name=tenant_schema,
            table_name=metadata["table_name"],
            user_id=user_id,
            scope=scope,
            field_access=permission_set.field_permissions
        )
        
        # Convert filters
        sql_filters = []
        if request.filters:
            sql_filters = [SQLQueryFilter(f.field, f.operator, f.value) for f in request.filters]
        
        having_filters = []
        if request.having:
            having_filters = [SQLQueryFilter(f.field, f.operator, f.value) for f in request.having]
        
        # Convert aggregations
        agg_specs = []
        for agg in request.aggregations:
            agg_specs.append({
                "field": agg.field,
                "function": agg.function,
                "alias": agg.alias or f"{agg.function}_{agg.field}"
            })
        
        # Convert order_by
        order_by = None
        if request.order_by:
            order_by = [(item["field"], item["direction"]) for item in request.order_by]
        
        # Build aggregate query
        sql, params = query_builder.build_aggregate(
            aggregations=agg_specs,
            group_by=request.group_by,
            filters=sql_filters,
            having=having_filters,
            order_by=order_by,
            limit=request.limit,
            offset=request.offset
        )
        
        # Execute query
        results = db.execute(text(sql), params).fetchall()
        
        # Convert to response
        result_list = []
        for row in results:
            result_list.append(dict(row._mapping))
        
        return AggregateQueryResponse(
            results=result_list,
            total=len(result_list)
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
)
    except Exception as e:
        logger.error(f"Error executing aggregate query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute aggregate query: {str(e)}"
        )


# ============================================================================
# Export/Import Endpoints
# ============================================================================

@router.post(
    "/export",
    response_model=ExportResponse,
    summary="Export data to CSV/JSON/Excel",
    responses={
        200: {"description": "Export completed successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"}
    }
)
async def export_data(
    request: ExportRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Export data to specified format.
    
    Permissions required:
    - data:read:* or data:read:{object_name}
    - bulk:export:format:{format} (e.g., bulk:export:format:csv)
    
    Supported formats:
    - csv: Comma-separated values
    - json: JSON array of objects
    - excel: Excel workbook (XLSX)
    
    Maximum 100,000 records per export.
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, request.object_name
        )
        
        # Check permissions
        perm_service = get_permission_service(db)
        all_fields = list(metadata["fields"].keys()) if metadata["fields"] else []
        permission_set = perm_service.get_user_permissions(user_id, object_id, all_fields)
        
        # Check read permission
        if not PermissionChecker.has_permission(permission_set.permissions, "data:read:*"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to read records"
            )
        
        # Check export format permission
        allowed_formats = PermissionChecker.get_export_formats(permission_set.permissions)
        if request.format not in allowed_formats and "*" not in allowed_formats:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have permission to export to {request.format} format"
            )
        
        scope = PermissionChecker.get_data_scope(permission_set.permissions, "read")
        
        query_builder = SecureQueryBuilder(
            schema_name=tenant_schema,
            table_name=metadata["table_name"],
            user_id=user_id,
            scope=scope,
            field_access=permission_set.field_permissions
        )
        
        # Convert filters
        sql_filters = []
        if request.filters:
            sql_filters = [SQLQueryFilter(f.field, f.operator, f.value) for f in request.filters]
        
        # Convert order_by
        order_by = None
        if request.order_by:
            order_by = [(item["field"], item["direction"]) for item in request.order_by]
        
        # Build select query
        sql, params = query_builder.build_select(
            filters=sql_filters,
            order_by=order_by,
            limit=request.limit
        )
        
        # Execute query
        results = db.execute(text(sql), params).fetchall()
        
        # Determine which fields to export
        if request.fields:
            # Validate requested fields are readable
            for field in request.fields:
                access = permission_set.field_permissions.get(field, FieldAccess.HIDE)
                if access == FieldAccess.HIDE:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"You do not have permission to export field: {field}"
                    )
            export_fields = request.fields
        else:
            # Export all readable fields
            export_fields = [
                field for field, access in permission_set.field_permissions.items()
                if access in (FieldAccess.READ, FieldAccess.WRITE, FieldAccess.MASK)
            ]
        
        # Convert to export format
        if request.format == "csv":
            export_data = _export_to_csv(results, export_fields)
            content_type = "text/csv"
        elif request.format == "json":
            export_data = _export_to_json(results, export_fields)
            content_type = "application/json"
        elif request.format == "excel":
            export_data = _export_to_excel(results, export_fields)
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported export format: {request.format}"
            )
        
        # Encode as base64
        encoded_data = base64.b64encode(export_data).decode('utf-8')
        
        return ExportResponse(
            data=encoded_data,
            format=request.format,
            record_count=len(results),
            size_bytes=len(export_data)
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error exporting data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export data: {str(e)}"
        )


@router.post(
    "/import",
    response_model=ImportResponse,
    summary="Import data from CSV/JSON",
    responses={
        200: {"description": "Import completed successfully"},
        403: {"model": ErrorResponse, "description": "Permission denied"}
    }
)
async def import_data(
    request: ImportRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Import data from file.
    
    Permissions required:
    - bulk:import:* or bulk:import:{object_name}
    - field:write:* for each field being imported
    
    Modes:
    - insert: Insert new records only
    - upsert: Insert or update based on upsert_key
    - update: Update existing records only
    
    The data field should contain base64-encoded file content.
    """
    try:
        # Get object metadata
        object_id, metadata = await get_object_id_and_metadata(
            db, tenant_schema, request.object_name
        )
        
        # Check permissions
        perm_service = get_permission_service(db)
        all_fields = list(metadata["fields"].keys()) if metadata["fields"] else []
        permission_set = perm_service.get_user_permissions(user_id, object_id, all_fields)
        
        # Check import permission
        if not PermissionChecker.can_bulk_operation(permission_set.permissions, "import"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to import data"
            )
        
        scope = PermissionChecker.get_data_scope(permission_set.permissions, "create")
        
        query_builder = SecureQueryBuilder(
            schema_name=tenant_schema,
            table_name=metadata["table_name"],
            user_id=user_id,
            scope=scope,
            field_access=permission_set.field_permissions
        )
        
        # Decode file content
        try:
            file_content = base64.b64decode(request.data)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 data: {str(e)}"
            )
        
        # Parse file based on format
        if request.format == "csv":
            records, validation_errors = _parse_csv(file_content)
        elif request.format == "json":
            records, validation_errors = _parse_json(file_content)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported import format: {request.format}"
            )
        
        total_rows = len(records) + len(validation_errors)
        valid_rows = len(records)
        invalid_rows = len(validation_errors)
        
        # If validate_only, return without importing
        if request.validate_only:
            return ImportResponse(
                total_rows=total_rows,
                valid_rows=valid_rows,
                invalid_rows=invalid_rows,
                imported_count=0,
                validation_errors=validation_errors
            )
        
        # Import records
        imported_count = 0
        
        if request.mode == "insert":
            for record_data in records:
                try:
                    sql, params = query_builder.build_insert(record_data)
                    db.execute(text(sql), params)
                    imported_count += 1
                except Exception as e:
                    logger.warning(f"Failed to insert record: {e}")
                    # Continue with other records
        
        elif request.mode == "upsert":
            if not request.upsert_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="upsert_key is required for upsert mode"
                )
            # TODO: Implement upsert logic
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Upsert mode not yet implemented"
            )
        
        elif request.mode == "update":
            # TODO: Implement update logic
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Update mode not yet implemented"
            )
        
        db.commit()
        
        return ImportResponse(
            total_rows=total_rows,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            imported_count=imported_count,
            validation_errors=validation_errors
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error importing data: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import data: {str(e)}"
        )


# ============================================================================
# Helper Functions for Export/Import
# ============================================================================

def _export_to_csv(results, fields: list) -> bytes:
    """Export query results to CSV format."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    
    for row in results:
        row_dict = dict(row._mapping)
        # Only include requested fields
        filtered_row = {k: v for k, v in row_dict.items() if k in fields}
        writer.writerow(filtered_row)
    
    return output.getvalue().encode('utf-8')


def _export_to_json(results, fields: list) -> bytes:
    """Export query results to JSON format."""
    data = []
    for row in results:
        row_dict = dict(row._mapping)
        # Only include requested fields
        filtered_row = {k: v for k, v in row_dict.items() if k in fields}
        # Convert non-serializable types
        for key, value in filtered_row.items():
            if isinstance(value, (datetime, UUID)):
                filtered_row[key] = str(value)
        data.append(filtered_row)
    
    return json.dumps(data, indent=2).encode('utf-8')


def _export_to_excel(results, fields: list) -> bytes:
    """Export query results to Excel format."""
    # For now, return CSV format
    # TODO: Implement proper Excel export using openpyxl or xlsxwriter
    logger.warning("Excel export not fully implemented, returning CSV format")
    return _export_to_csv(results, fields)


def _parse_csv(file_content: bytes) -> tuple:
    """Parse CSV file content and return (records, validation_errors)."""
    validation_errors = []
    records = []
    
    try:
        content_str = file_content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(content_str))
        
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            if row:
                records.append(row)
    except Exception as e:
        validation_errors.append({
            "row": 1,
            "field": None,
            "message": f"Failed to parse CSV: {str(e)}"
        })
    
    return records, validation_errors


def _parse_json(file_content: bytes) -> tuple:
    """Parse JSON file content and return (records, validation_errors)."""
    validation_errors = []
    records = []
    
    try:
        content_str = file_content.decode('utf-8')
        data = json.loads(content_str)
        
        if not isinstance(data, list):
            validation_errors.append({
                "row": 1,
                "field": None,
                "message": "JSON must be an array of objects"
            })
        else:
            records = data
    except Exception as e:
        validation_errors.append({
            "row": 1,
            "field": None,
            "message": f"Failed to parse JSON: {str(e)}"
        })
    
    return records, validation_errors


