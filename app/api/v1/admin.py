"""Phase 4: Audit Log and Soft Delete API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List
import logging

from app.db.connection import get_tenant_db
from app.services.audit_logger import AuditLogger
from app.services.soft_delete import SoftDeleteService
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class AuditLogEntry(BaseModel):
    """Audit log entry response."""
    id: str
    action: str
    user_id: str
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    changed_fields: Optional[List[str]] = None
    timestamp: str
    ip_address: Optional[str] = None
    status: str


class DeletedRecordInfo(BaseModel):
    """Deleted record information."""
    record_id: str
    deleted_at: str
    deleted_by: str
    deletion_reason: Optional[str] = None
    undeleted_at: Optional[str] = None
    undeleted_by: Optional[str] = None
    days_until_permanent_delete: Optional[int] = None


class UndeleteRequest(BaseModel):
    """Request to restore a deleted record."""
    object_name: str = Field(..., description="Object name")
    record_id: UUID = Field(..., description="Record ID to restore")
    reason: Optional[str] = Field(None, description="Reason for restoration")


# ============================================================================
# Dependency: Get current user from request
# ============================================================================

def get_current_user(x_user_id: str = Header(..., alias="X-User-ID")) -> UUID:
    """Extract user ID from request header."""
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format"
        )


def get_tenant_schema(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """Extract tenant schema name from request header."""
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant ID"
        )
    return x_tenant_id


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@router.get(
    "/audit/record/{record_id}",
    response_model=List[AuditLogEntry],
    summary="Get audit history for a record",
    responses={
        200: {"description": "Audit history retrieved"},
        403: {"description": "Permission denied"}
    }
)
async def get_record_audit_history(
    record_id: UUID,
    limit: int = 100,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Get complete audit history for a specific record.
    
    Shows all create, update, delete operations performed on the record.
    Requires admin or audit:read permission.
    """
    try:
        # TODO: Check audit:read permission
        
        audit = AuditLogger(db)
        history = audit.get_record_history(
            tenant_id=tenant_schema,
            record_id=record_id,
            limit=limit
        )
        
        return [AuditLogEntry(**entry) for entry in history]
        
    except Exception as e:
        logger.error(f"Error retrieving audit history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit history: {str(e)}"
        )


@router.get(
    "/audit/user/{user_id}/activity",
    summary="Get user activity summary",
    responses={
        200: {"description": "Activity summary retrieved"},
        403: {"description": "Permission denied"}
    }
)
async def get_user_activity_summary(
    target_user_id: UUID,
    days: int = 30,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Get activity summary for a user.
    
    Shows operation counts by action and object.
    Requires admin or audit:read permission.
    """
    try:
        # TODO: Check audit:read permission
        # Users can view own activity, admins can view any user
        
        audit = AuditLogger(db)
        summary = audit.get_user_activity(
            tenant_id=tenant_schema,
            user_id=target_user_id,
            days=days
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"Error retrieving user activity: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user activity: {str(e)}"
        )


# ============================================================================
# Soft Delete Endpoints
# ============================================================================

@router.get(
    "/deleted/{object_name}",
    response_model=List[DeletedRecordInfo],
    summary="Get deleted records for an object",
    responses={
        200: {"description": "Deleted records retrieved"},
        403: {"description": "Permission denied"}
    }
)
async def get_deleted_records(
    object_name: str,
    include_restored: bool = False,
    limit: int = 100,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Get list of soft-deleted records for an object.
    
    Allows administrators to see what has been deleted and
    when it will be permanently deleted.
    
    Requires admin or data:admin permission.
    """
    try:
        # TODO: Check data:admin permission
        
        soft_delete = SoftDeleteService(db)
        records = soft_delete.get_deleted_records(
            tenant_id=tenant_schema,
            object_name=object_name,
            include_restored=include_restored,
            limit=limit
        )
        
        return [DeletedRecordInfo(**record) for record in records]
        
    except Exception as e:
        logger.error(f"Error retrieving deleted records: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve deleted records: {str(e)}"
        )


@router.post(
    "/undelete",
    status_code=status.HTTP_200_OK,
    summary="Restore a deleted record",
    responses={
        200: {"description": "Record restored successfully"},
        403: {"description": "Permission denied"},
        404: {"description": "Record not found or already active"}
    }
)
async def undelete_record(
    request: UndeleteRequest,
    user_id: UUID = Depends(get_current_user),
    tenant_schema: str = Depends(get_tenant_schema),
    db: Session = Depends(get_tenant_db)
):
    """
    Restore a soft-deleted record.
    
    Makes the record active again.
    Requires data:undelete permission.
    """
    try:
        # TODO: Check data:undelete permission
        
        soft_delete = SoftDeleteService(db)
        success = soft_delete.undelete(
            tenant_id=tenant_schema,
            object_name=request.object_name,
            record_id=request.record_id,
            undeleted_by=user_id,
            undelete_reason=request.reason
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Record not found or cannot be restored"
            )
        
        # Log the undelete operation
        # TODO: Get object_id
        # audit.log_operation(
        #     tenant_id=tenant_schema,
        #     user_id=user_id,
        #     action="undelete",
        #     object_id=object_id,
        #     object_name=request.object_name,
        #     record_id=request.record_id
        # )
        
        return {"message": "Record restored successfully", "record_id": str(request.record_id)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring record: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore record: {str(e)}"
        )
