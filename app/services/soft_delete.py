"""Soft delete service for recoverable record deletion."""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json
from fastapi import Depends

from app.db.connection import get_tenant_db

logger = logging.getLogger(__name__)


class SoftDeleteService:
    """
    Service for managing soft deletes (recoverable deletions).
    
    Features:
    - Mark records as deleted without removing from database
    - Restore deleted records
    - Automatic filtering of deleted records in queries
    - Scheduled permanent deletion after retention period
    """
    
    def __init__(self, db: Session):
        """
        Initialize soft delete service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def soft_delete(
        self,
        tenant_id: str,
        object_name: str,
        record_id: UUID,
        deleted_by: UUID,
        deletion_reason: Optional[str] = None
    ) -> bool:
        """
        Soft delete a record.
        
        Args:
            tenant_id: Tenant schema name
            object_name: Table name
            record_id: Record ID to delete
            deleted_by: User performing the deletion
            deletion_reason: Optional reason for deletion
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Call database function
            sql = text("""
                SELECT soft_delete_record(
                    :tenant_id,
                    :object_name,
                    :record_id,
                    :deleted_by,
                    :deletion_reason
                ) as success
            """)
            
            result = self.db.execute(sql, {
                "tenant_id": tenant_id,
                "object_name": object_name,
                "record_id": str(record_id),
                "deleted_by": str(deleted_by),
                "deletion_reason": deletion_reason
            })
            
            success = result.fetchone().success
            self.db.commit()
            
            if success:
                logger.info(f"Soft deleted record {record_id} from {tenant_id}.{object_name}")
            else:
                logger.warning(f"Failed to soft delete record {record_id} (may already be deleted)")
            
            return success
            
        except Exception as e:
            logger.error(f"Error soft deleting record: {e}", exc_info=True)
            self.db.rollback()
            raise
    
    def undelete(
        self,
        tenant_id: str,
        object_name: str,
        record_id: UUID,
        undeleted_by: UUID,
        undelete_reason: Optional[str] = None
    ) -> bool:
        """
        Restore a soft-deleted record.
        
        Args:
            tenant_id: Tenant schema name
            object_name: Table name
            record_id: Record ID to restore
            undeleted_by: User performing the restoration
            undelete_reason: Optional reason for restoration
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Call database function
            sql = text("""
                SELECT undelete_record(
                    :tenant_id,
                    :object_name,
                    :record_id,
                    :undeleted_by,
                    :undelete_reason
                ) as success
            """)
            
            result = self.db.execute(sql, {
                "tenant_id": tenant_id,
                "object_name": object_name,
                "record_id": str(record_id),
                "undeleted_by": str(undeleted_by),
                "undelete_reason": undelete_reason
            })
            
            success = result.fetchone().success
            self.db.commit()
            
            if success:
                logger.info(f"Restored record {record_id} in {tenant_id}.{object_name}")
            else:
                logger.warning(f"Failed to restore record {record_id} (may not be deleted or undelete not allowed)")
            
            return success
            
        except Exception as e:
            logger.error(f"Error restoring record: {e}", exc_info=True)
            self.db.rollback()
            raise
    
    def get_deleted_records(
        self,
        tenant_id: str,
        object_name: str,
        include_restored: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get list of deleted records for an object.
        
        Args:
            tenant_id: Tenant identifier
            object_name: Object name
            include_restored: Include previously restored records
            limit: Maximum records to return
            
        Returns:
            List of deleted record information
        """
        sql = text("""
            SELECT * FROM get_deleted_records(
                :tenant_id,
                :object_name,
                :include_restored,
                :limit
            )
        """)
        
        result = self.db.execute(sql, {
            "tenant_id": tenant_id,
            "object_name": object_name,
            "include_restored": include_restored,
            "limit": limit
        })
        
        records = []
        for row in result:
            records.append({
                "record_id": str(row.record_id),
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
                "deleted_by": str(row.deleted_by),
                "deletion_reason": row.deletion_reason,
                "undeleted_at": row.undeleted_at.isoformat() if row.undeleted_at else None,
                "undeleted_by": str(row.undeleted_by) if row.undeleted_by else None,
                "days_until_permanent_delete": row.days_until_permanent_delete
            })
        
        return records
    
    def configure_soft_deletes(
        self,
        tenant_id: str,
        object_id: UUID,
        enabled: bool = True,
        permanent_delete_after_days: Optional[int] = None,
        allow_undelete: bool = True,
        require_permission_to_undelete: bool = True
    ) -> UUID:
        """
        Configure soft delete behavior for an object.
        
        Args:
            tenant_id: Tenant identifier
            object_id: Object metadata ID
            enabled: Whether soft deletes are enabled
            permanent_delete_after_days: Days before permanent deletion (None = never)
            allow_undelete: Allow restoring deleted records
            require_permission_to_undelete: Require explicit permission to undelete
            
        Returns:
            Configuration ID
        """
        sql = text("""
            INSERT INTO sys_soft_delete_config (
                tenant_id, object_id, enabled,
                permanent_delete_after_days,
                allow_undelete, require_permission_to_undelete
            ) VALUES (
                :tenant_id, :object_id, :enabled,
                :permanent_delete_after_days,
                :allow_undelete, :require_permission_to_undelete
            )
            ON CONFLICT (tenant_id, object_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                permanent_delete_after_days = EXCLUDED.permanent_delete_after_days,
                allow_undelete = EXCLUDED.allow_undelete,
                require_permission_to_undelete = EXCLUDED.require_permission_to_undelete,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """)
        
        result = self.db.execute(sql, {
            "tenant_id": tenant_id,
            "object_id": str(object_id),
            "enabled": enabled,
            "permanent_delete_after_days": permanent_delete_after_days,
            "allow_undelete": allow_undelete,
            "require_permission_to_undelete": require_permission_to_undelete
        })
        
        config_id = result.fetchone()[0]
        self.db.commit()
        
        logger.info(f"Configured soft deletes for object {object_id} in tenant {tenant_id}")
        return UUID(config_id)
    
    def add_soft_delete_columns(
        self,
        tenant_id: str,
        table_name: str
    ) -> bool:
        """
        Add soft delete columns to an existing table.
        
        Args:
            tenant_id: Tenant schema name
            table_name: Table name
            
        Returns:
            True if successful
        """
        try:
            sql = text("""
                SELECT add_soft_delete_columns_to_table(
                    :tenant_id,
                    :table_name
                ) as success
            """)
            
            result = self.db.execute(sql, {
                "tenant_id": tenant_id,
                "table_name": table_name
            })
            
            success = result.fetchone().success
            self.db.commit()
            
            if success:
                logger.info(f"Added soft delete columns to {tenant_id}.{table_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error adding soft delete columns: {e}", exc_info=True)
            self.db.rollback()
            return False
    
    def permanent_delete_old_records(self) -> int:
        """
        Permanently delete records past their retention period.
        
        This should be called periodically (e.g., daily cron job).
        
        Returns:
            Number of records permanently deleted
        """
        try:
            sql = text("SELECT permanent_delete_old_records() as count")
            result = self.db.execute(sql)
            count = result.fetchone().count
            self.db.commit()
            
            if count > 0:
                logger.info(f"Permanently deleted {count} old records")
            
            return count
            
        except Exception as e:
            logger.error(f"Error permanently deleting old records: {e}", exc_info=True)
            self.db.rollback()
            return 0
    
    def is_soft_delete_enabled(
        self,
        tenant_id: str,
        object_id: UUID
    ) -> bool:
        """
        Check if soft deletes are enabled for an object.
        
        Args:
            tenant_id: Tenant identifier
            object_id: Object metadata ID
            
        Returns:
            True if soft deletes are enabled
        """
        sql = text("""
            SELECT enabled
            FROM sys_soft_delete_config
            WHERE tenant_id = :tenant_id
              AND object_id = :object_id
        """)
        
        result = self.db.execute(sql, {
            "tenant_id": tenant_id,
            "object_id": str(object_id)
        })
        
        row = result.fetchone()
        return row.enabled if row else True  # Default to enabled


def get_soft_delete_service(db: Session = Depends(get_tenant_db)) -> SoftDeleteService:
    """
    Dependency injection function for FastAPI.
    
    Usage:
        soft_delete = Depends(get_soft_delete_service)
    """
    return SoftDeleteService(db)
