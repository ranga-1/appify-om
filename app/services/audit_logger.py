"""Audit logging service for tracking all data operations."""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json
from contextvars import ContextVar
from fastapi import Depends

from app.db.connection import get_tenant_db

logger = logging.getLogger(__name__)

# Context vars for tracking request context
request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


class AuditLogger:
    """
    Service for logging all data operations to audit trail.
    
    Features:
    - Tracks all CRUD operations
    - Records user, timestamp, IP address
    - Stores old and new values for changes
    - Supports bulk operations
    - Async logging (doesn't block main operations)
    """
    
    def __init__(self, db: Session):
        """
        Initialize audit logger.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def log_operation(
        self,
        tenant_id: str,
        user_id: UUID,
        action: str,
        object_id: UUID,
        object_name: str,
        record_id: Optional[UUID] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        affected_count: int = 1,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Log a data operation to audit trail.
        
        Args:
            tenant_id: Tenant identifier
            user_id: User who performed the operation
            action: Operation type (create, read, update, delete, etc.)
            object_id: Object metadata ID
            object_name: Object name
            record_id: ID of affected record (None for bulk ops)
            old_values: Previous state (for updates/deletes)
            new_values: New state (for creates/updates)
            status: Operation status (success, failed, partial)
            error_message: Error message if failed
            affected_count: Number of records affected
            duration_ms: Operation duration in milliseconds
            metadata: Additional context
            
        Returns:
            UUID of created audit log entry
        """
        try:
            # Get request context
            ctx = request_context.get({})
            
            # Calculate changed fields
            changed_fields = None
            if old_values and new_values:
                changed_fields = [
                    field for field in new_values.keys()
                    if field in old_values and old_values[field] != new_values[field]
                ]
            
            # Prepare SQL
            sql = text("""
                INSERT INTO sys_audit_log (
                    tenant_id, user_id, session_id,
                    action, object_id, object_name, record_id,
                    old_values, new_values, changed_fields,
                    ip_address, user_agent, request_id, endpoint, http_method,
                    status, error_message, affected_count, duration_ms, metadata
                ) VALUES (
                    :tenant_id, :user_id, :session_id,
                    :action, :object_id, :object_name, :record_id,
                    :old_values, :new_values, :changed_fields,
                    :ip_address, :user_agent, :request_id, :endpoint, :http_method,
                    :status, :error_message, :affected_count, :duration_ms, :metadata
                )
                RETURNING id
            """)
            
            # Execute insert
            result = self.db.execute(sql, {
                "tenant_id": tenant_id,
                "user_id": str(user_id),
                "session_id": ctx.get("session_id"),
                "action": action,
                "object_id": str(object_id),
                "object_name": object_name,
                "record_id": str(record_id) if record_id else None,
                "old_values": json.dumps(old_values) if old_values else None,
                "new_values": json.dumps(new_values) if new_values else None,
                "changed_fields": changed_fields,
                "ip_address": ctx.get("ip_address"),
                "user_agent": ctx.get("user_agent"),
                "request_id": ctx.get("request_id"),
                "endpoint": ctx.get("endpoint"),
                "http_method": ctx.get("http_method"),
                "status": status,
                "error_message": error_message,
                "affected_count": affected_count,
                "duration_ms": duration_ms,
                "metadata": json.dumps(metadata) if metadata else None
            })
            
            audit_id = result.fetchone()[0]
            self.db.commit()
            
            logger.debug(f"Audit log created: {audit_id} for action {action} on {object_name}")
            return UUID(audit_id)
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}", exc_info=True)
            # Don't fail the main operation if audit logging fails
            self.db.rollback()
            return None
    
    def log_create(
        self,
        tenant_id: str,
        user_id: UUID,
        object_id: UUID,
        object_name: str,
        record_id: UUID,
        data: Dict[str, Any],
        duration_ms: Optional[int] = None
    ) -> UUID:
        """Log a create operation."""
        return self.log_operation(
            tenant_id=tenant_id,
            user_id=user_id,
            action="create",
            object_id=object_id,
            object_name=object_name,
            record_id=record_id,
            new_values=data,
            duration_ms=duration_ms
        )
    
    def log_update(
        self,
        tenant_id: str,
        user_id: UUID,
        object_id: UUID,
        object_name: str,
        record_id: UUID,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
        duration_ms: Optional[int] = None
    ) -> UUID:
        """Log an update operation."""
        return self.log_operation(
            tenant_id=tenant_id,
            user_id=user_id,
            action="update",
            object_id=object_id,
            object_name=object_name,
            record_id=record_id,
            old_values=old_data,
            new_values=new_data,
            duration_ms=duration_ms
        )
    
    def log_delete(
        self,
        tenant_id: str,
        user_id: UUID,
        object_id: UUID,
        object_name: str,
        record_id: UUID,
        data: Dict[str, Any],
        duration_ms: Optional[int] = None
    ) -> UUID:
        """Log a delete operation."""
        return self.log_operation(
            tenant_id=tenant_id,
            user_id=user_id,
            action="delete",
            object_id=object_id,
            object_name=object_name,
            record_id=record_id,
            old_values=data,
            duration_ms=duration_ms
        )
    
    def log_bulk_operation(
        self,
        tenant_id: str,
        user_id: UUID,
        action: str,
        object_id: UUID,
        object_name: str,
        affected_count: int,
        filters: Optional[List[Dict[str, Any]]] = None,
        data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None
    ) -> UUID:
        """Log a bulk operation."""
        metadata = {}
        if filters:
            metadata["filters"] = filters
        
        return self.log_operation(
            tenant_id=tenant_id,
            user_id=user_id,
            action=f"bulk_{action}",
            object_id=object_id,
            object_name=object_name,
            record_id=None,
            new_values=data if action == "update" else None,
            affected_count=affected_count,
            metadata=metadata,
            duration_ms=duration_ms
        )
    
    def get_record_history(
        self,
        tenant_id: str,
        record_id: UUID,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit history for a specific record.
        
        Args:
            tenant_id: Tenant identifier
            record_id: Record ID
            limit: Maximum entries to return
            
        Returns:
            List of audit log entries
        """
        sql = text("""
            SELECT 
                id, action, user_id,
                old_values, new_values, changed_fields,
                created_at, ip_address, status
            FROM sys_audit_log
            WHERE tenant_id = :tenant_id
              AND record_id = :record_id
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        
        result = self.db.execute(sql, {
            "tenant_id": tenant_id,
            "record_id": str(record_id),
            "limit": limit
        })
        
        entries = []
        for row in result:
            entries.append({
                "id": str(row.id),
                "action": row.action,
                "user_id": str(row.user_id),
                "old_values": json.loads(row.old_values) if row.old_values else None,
                "new_values": json.loads(row.new_values) if row.new_values else None,
                "changed_fields": row.changed_fields,
                "timestamp": row.created_at.isoformat(),
                "ip_address": str(row.ip_address) if row.ip_address else None,
                "status": row.status
            })
        
        return entries
    
    def get_user_activity(
        self,
        tenant_id: str,
        user_id: UUID,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get activity summary for a user.
        
        Args:
            tenant_id: Tenant identifier
            user_id: User ID
            days: Number of days to look back
            
        Returns:
            Activity summary with operation counts
        """
        sql = text("""
            SELECT 
                action,
                object_name,
                COUNT(*) as operation_count,
                COUNT(*) FILTER (WHERE status = 'success') as success_count,
                COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
                SUM(affected_count) as total_affected
            FROM sys_audit_log
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND created_at >= CURRENT_TIMESTAMP - INTERVAL ':days days'
            GROUP BY action, object_name
            ORDER BY operation_count DESC
        """)
        
        result = self.db.execute(sql, {
            "tenant_id": tenant_id,
            "user_id": str(user_id),
            "days": days
        })
        
        summary = []
        for row in result:
            summary.append({
                "action": row.action,
                "object_name": row.object_name,
                "operation_count": row.operation_count,
                "success_count": row.success_count,
                "failed_count": row.failed_count,
                "total_affected": row.total_affected
            })
        
        return {
            "user_id": str(user_id),
            "period_days": days,
            "activity": summary
        }


def set_request_context(
    session_id: Optional[UUID] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[UUID] = None,
    endpoint: Optional[str] = None,
    http_method: Optional[str] = None
):
    """
    Set request context for audit logging.
    
    This should be called at the start of each request to capture
    context information for all audit logs created during that request.
    """
    request_context.set({
        "session_id": str(session_id) if session_id else None,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "request_id": str(request_id) if request_id else None,
        "endpoint": endpoint,
        "http_method": http_method
    })


def get_audit_logger(db: Session = Depends(get_tenant_db)) -> AuditLogger:
    """
    Dependency injection function for FastAPI.
    
    Usage:
        audit = Depends(get_audit_logger)
    """
    return AuditLogger(db)
