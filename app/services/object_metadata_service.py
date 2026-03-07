"""Service layer for Object Metadata operations."""

import logging
import re
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2.extras
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

from app.db.connection import db_manager
from app.models.object_metadata import (
    ObjectMetadataCreate,
    ObjectMetadataUpdate,
    ObjectMetadataResponse
)

logger = logging.getLogger(__name__)


class ObjectMetadataService:
    """Service for managing object metadata."""
    
    @staticmethod
    def _sanitize_label_to_api_name(label: str, prefix: str) -> str:
        """
        Convert label to valid SQL table name with prefix.
        
        Rules:
        - Lowercase
        - Spaces → underscore
        - Invalid chars → underscore
        - Remove duplicate underscores
        - Prefix with customer prefix
        
        Example: "Customer Account" + "abc12" → "abc12_customer_account"
        
        Args:
            label: Display label
            prefix: Customer prefix (5-char alphanumeric)
            
        Returns:
            Valid SQL table name
        """
        # Strip and lowercase
        sanitized = label.strip().lower()
        
        # Replace multiple spaces with single underscore
        sanitized = re.sub(r'\s+', '_', sanitized)
        
        # Keep only valid chars: a-z, 0-9, _ (replace others with _)
        sanitized = re.sub(r'[^a-z0-9_]', '_', sanitized)
        
        # Remove duplicate underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        
        # Add prefix
        api_name = f"{prefix.lower()}_{sanitized}"
        logger.debug(f"Sanitized label '{label}' to api_name '{api_name}'")
        return api_name
    
    def _get_connection_and_schema(
        self, user_role: str, customer_id: Optional[str]
    ) -> Tuple:
        """
        Determine database connection and schema based on user role.
        
        Args:
            user_role: 'appify-admin' or 'customer-admin'
            customer_id: Customer ID for tenant schema
            
        Returns:
            Tuple of (connection, schema_name, db_type)
        """
        if user_role == "appify-admin":
            conn = db_manager.get_core_connection()
            schema = "public"
            return (conn, schema, "core")
        else:  # customer-admin
            conn = db_manager.get_tenants_connection()
            schema = f"tenant_{customer_id}"
            return (conn, schema, "tenants")
    
    def get_all(
        self,
        user_role: str,
        customer_id: Optional[str],
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[ObjectMetadataResponse], int]:
        """
        Get paginated list of object metadata.
        
        Args:
            user_role: User's role
            customer_id: Customer ID
            skip: Number of records to skip
            limit: Maximum records to return
            
        Returns:
            Tuple of (list of objects, total count)
        """
        conn, schema, db_type = self._get_connection_and_schema(
            user_role, customer_id
        )
        
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Count total
            cur.execute(
                f"SELECT COUNT(*) as count FROM {schema}.sys_object_metadata"
            )
            total = cur.fetchone()['count']
            
            # Get paginated results
            query = f"""
                SELECT id, label, api_name, description, 
                       used_in_global_search, enable_audit, is_remote_object,
                       fields, dependencies, uniqueness, reference_controls,
                       advanced_search, validation_rules, status,
                       deployment_started_date, table_created_date, table_name,
                       deployment_error, created_by, created_date, modified_by, modified_date
                FROM {schema}.sys_object_metadata
                ORDER BY created_date DESC
                LIMIT %s OFFSET %s
            """
            cur.execute(query, (limit, skip))
            rows = cur.fetchall()
            
            items = [ObjectMetadataResponse(**row) for row in rows]
            
            cur.close()
            logger.info(
                f"Retrieved {len(items)} of {total} objects from {schema}"
            )
            return (items, total)
            
        finally:
            if db_type == "core":
                db_manager.return_core_connection(conn)
            else:
                db_manager.return_tenants_connection(conn)
    
    def get_by_id(
        self,
        object_id: UUID,
        user_role: str,
        customer_id: Optional[str]
    ) -> Optional[ObjectMetadataResponse]:
        """
        Get single object metadata by ID.
        
        Args:
            object_id: Object UUID
            user_role: User's role
            customer_id: Customer ID
            
        Returns:
            Object metadata or None if not found
        """
        conn, schema, db_type = self._get_connection_and_schema(
            user_role, customer_id
        )
        
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = f"""
                SELECT id, label, api_name, description,
                       used_in_global_search, enable_audit, is_remote_object,
                       fields, dependencies, uniqueness, reference_controls,
                       advanced_search, validation_rules, status,
                       deployment_started_date, table_created_date, table_name,
                       deployment_error, created_by, created_date, modified_by, modified_date
                FROM {schema}.sys_object_metadata
                WHERE id = %s
            """
            cur.execute(query, (str(object_id),))
            row = cur.fetchone()
            
            cur.close()
            
            if row:
                logger.info(f"Found object {object_id} in {schema}")
                return ObjectMetadataResponse(**row)
            
            logger.warning(f"Object {object_id} not found in {schema}")
            return None
            
        finally:
            if db_type == "core":
                db_manager.return_core_connection(conn)
            else:
                db_manager.return_tenants_connection(conn)
    
    def create(
        self,
        data: ObjectMetadataCreate,
        user_id: str,
        user_role: str,
        customer_id: Optional[str],
        customer_prefix: str
    ) -> ObjectMetadataResponse:
        """
        Create new object metadata.
        
        Args:
            data: Object metadata to create
            user_id: User ID creating the object
            user_role: User's role
            customer_id: Customer ID
            customer_prefix: Customer's unique prefix
            
        Returns:
            Created object metadata
            
        Raises:
            ValueError: If api_name already exists
        """
        conn, schema, db_type = self._get_connection_and_schema(
            user_role, customer_id
        )
        
        try:
            conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Generate api_name
            api_name = self._sanitize_label_to_api_name(
                data.label, customer_prefix
            )
            
            # Check uniqueness
            cur.execute(
                f"SELECT COUNT(*) as count FROM {schema}.sys_object_metadata "
                f"WHERE api_name = %s",
                (api_name,)
            )
            if cur.fetchone()['count'] > 0:
                raise ValueError(
                    f"Object with api_name '{api_name}' already exists"
                )
            
            # Insert
            query = f"""
                INSERT INTO {schema}.sys_object_metadata 
                (label, api_name, description, used_in_global_search, enable_audit,
                 is_remote_object, fields, dependencies, uniqueness, reference_controls,
                 advanced_search, validation_rules, created_by, modified_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, label, api_name, description, used_in_global_search,
                          enable_audit, is_remote_object, fields, dependencies,
                          uniqueness, reference_controls, advanced_search, validation_rules,
                          status, deployment_started_date, table_created_date, table_name,
                          deployment_error, created_by, created_date, modified_by, modified_date
            """
            
            cur.execute(query, (
                data.label,
                api_name,
                data.description,
                data.used_in_global_search,
                data.enable_audit,
                data.is_remote_object,
                psycopg2.extras.Json(data.fields),
                psycopg2.extras.Json(data.dependencies) if data.dependencies else None,
                psycopg2.extras.Json(data.uniqueness) if data.uniqueness else None,
                psycopg2.extras.Json(data.reference_controls) if data.reference_controls else None,
                psycopg2.extras.Json(data.advanced_search) if data.advanced_search else None,
                psycopg2.extras.Json(data.validation_rules) if data.validation_rules else None,
                user_id,
                user_id
            ))
            
            row = cur.fetchone()
            conn.commit()
            cur.close()
            
            logger.info(
                f"Created object '{api_name}' in {schema} by user {user_id}"
            )
            return ObjectMetadataResponse(**row)
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create object in {schema}: {e}")
            raise
        finally:
            if db_type == "core":
                db_manager.return_core_connection(conn)
            else:
                db_manager.return_tenants_connection(conn)
    
    def update(
        self,
        object_id: UUID,
        data: ObjectMetadataUpdate,
        user_id: str,
        user_role: str,
        customer_id: Optional[str],
        customer_prefix: str
    ) -> Optional[ObjectMetadataResponse]:
        """
        Update existing object metadata.
        
        Args:
            object_id: Object UUID to update
            data: Updated object metadata
            user_id: User ID updating the object
            user_role: User's role
            customer_id: Customer ID
            customer_prefix: Customer's unique prefix
            
        Returns:
            Updated object metadata or None if not found
            
        Raises:
            ValueError: If new api_name conflicts with existing
        """
        conn, schema, db_type = self._get_connection_and_schema(
            user_role, customer_id
        )
        
        try:
            conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Build update fields
            updates = []
            params = []
            
            # If label changed, regenerate api_name
            new_api_name = None
            if data.label is not None:
                new_api_name = self._sanitize_label_to_api_name(
                    data.label, customer_prefix
                )
                
                # Check uniqueness (exclude current record)
                cur.execute(
                    f"SELECT COUNT(*) as count FROM {schema}.sys_object_metadata "
                    f"WHERE api_name = %s AND id != %s",
                    (new_api_name, str(object_id))
                )
                if cur.fetchone()['count'] > 0:
                    raise ValueError(
                        f"Object with api_name '{new_api_name}' already exists"
                    )
                
                updates.append("label = %s")
                params.append(data.label)
                updates.append("api_name = %s")
                params.append(new_api_name)
            
            if data.description is not None:
                updates.append("description = %s")
                params.append(data.description)
            
            if data.used_in_global_search is not None:
                updates.append("used_in_global_search = %s")
                params.append(data.used_in_global_search)
            
            if data.enable_audit is not None:
                updates.append("enable_audit = %s")
                params.append(data.enable_audit)
            
            if data.is_remote_object is not None:
                updates.append("is_remote_object = %s")
                params.append(data.is_remote_object)
            
            if data.fields is not None:
                updates.append("fields = %s")
                params.append(psycopg2.extras.Json(data.fields))
            
            if data.dependencies is not None:
                updates.append("dependencies = %s")
                params.append(psycopg2.extras.Json(data.dependencies) if data.dependencies else None)
            
            if data.uniqueness is not None:
                updates.append("uniqueness = %s")
                params.append(psycopg2.extras.Json(data.uniqueness) if data.uniqueness else None)
            
            if data.reference_controls is not None:
                updates.append("reference_controls = %s")
                params.append(psycopg2.extras.Json(data.reference_controls) if data.reference_controls else None)
            
            if data.advanced_search is not None:
                updates.append("advanced_search = %s")
                params.append(psycopg2.extras.Json(data.advanced_search) if data.advanced_search else None)
            
            if data.validation_rules is not None:
                updates.append("validation_rules = %s")
                params.append(psycopg2.extras.Json(data.validation_rules) if data.validation_rules else None)
            
            if not updates:
                # No changes, return current record
                cur.close()
                return self.get_by_id(object_id, user_role, customer_id)
            
            # Add modified_by
            updates.append("modified_by = %s")
            params.append(user_id)
            
            # Build query
            query = f"""
                UPDATE {schema}.sys_object_metadata
                SET {', '.join(updates)}
                WHERE id = %s
                RETURNING id, label, api_name, description, used_in_global_search,
                          enable_audit, is_remote_object, fields, dependencies,
                          uniqueness, reference_controls, advanced_search, validation_rules,
                          status, deployment_started_date, table_created_date, table_name,
                          deployment_error, created_by, created_date, modified_by, modified_date
            """
            params.append(str(object_id))
            
            cur.execute(query, params)
            row = cur.fetchone()
            
            if not row:
                conn.rollback()
                cur.close()
                logger.warning(f"Object {object_id} not found in {schema}")
                return None
            
            conn.commit()
            cur.close()
            
            logger.info(
                f"Updated object {object_id} in {schema} by user {user_id}"
            )
            return ObjectMetadataResponse(**row)
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update object {object_id} in {schema}: {e}")
            raise
        finally:
            if db_type == "core":
                db_manager.return_core_connection(conn)
            else:
                db_manager.return_tenants_connection(conn)
