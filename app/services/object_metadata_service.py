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
    
    def _validate_deployed_object_update(
        self,
        existing: Dict,
        data: ObjectMetadataUpdate
    ) -> None:
        """
        Validate updates to deployed objects (status='created' or 'modified').
        
        When an object is deployed, only allow changes that don't affect table structure:
        - DENY: Changing api_name (table name)
        - DENY: Changing field api_name (column name)
        - DENY: Changing field type (column data type)
        - ALLOW: Everything else (labels, descriptions, adding/removing fields, etc.)
        
        Args:
            existing: Current object metadata from database
            data: Update request data
            
        Raises:
            ValueError: If attempting restricted changes
        """
        import json
        
        # Only validate if fields are being updated
        if data.fields is None:
            return
        
        existing_fields = existing.get('fields', [])
        new_fields = data.fields
        
        # Create maps of existing fields by api_name for quick lookup
        existing_fields_map = {f['api_name']: f for f in existing_fields if 'api_name' in f}
        new_fields_map = {f['api_name']: f for f in new_fields if 'api_name' in f}
        
        # Check for changes to existing fields
        for api_name, existing_field in existing_fields_map.items():
            if api_name in new_fields_map:
                new_field = new_fields_map[api_name]
                
                # Check if type changed
                existing_type = existing_field.get('type')
                new_type = new_field.get('type')
                
                if existing_type != new_type:
                    raise ValueError(
                        f"Cannot change field type for '{api_name}' from '{existing_type}' to '{new_type}' "
                        f"on deployed object. Field types are immutable after deployment."
                    )
        
        # Note: We DO allow:
        # - Adding new fields (they will be added via ALTER TABLE on next deploy)
        # - Removing fields (mark_as_deleted, column persists)
        # - Changing field labels, descriptions, constraints, etc.
    
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
            ValueError: If attempting to change api_name or field types on deployed objects
        """
        conn, schema, db_type = self._get_connection_and_schema(
            user_role, customer_id
        )
        
        try:
            conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Fetch existing object to compare for changes and enforce immutability
            cur.execute(
                f"""SELECT label, api_name, description, used_in_global_search, 
                           enable_audit, is_remote_object, fields, dependencies, 
                           uniqueness, reference_controls, advanced_search, 
                           validation_rules, status
                    FROM {schema}.sys_object_metadata
                    WHERE id = %s""",
                (str(object_id),)
            )
            existing = cur.fetchone()
            
            if not existing:
                cur.close()
                logger.warning(f"Object {object_id} not found in {schema}")
                return None
            
            # Validate updates if object is deployed (status='created' or 'modified')
            if existing['status'] in ('created', 'modified'):
                self._validate_deployed_object_update(existing, data)
            
            # Build update fields
            updates = []
            params = []
            has_changes = False
            
            # Note: api_name is immutable and cannot be changed
            # It is NOT included in ObjectMetadataUpdate schema
            # Label can be changed freely - api_name stays the same
            
            # Label can be changed freely - api_name is NOT regenerated
            if data.label is not None and data.label != existing['label']:
                updates.append("label = %s")
                params.append(data.label)
                has_changes = True
            
            # Change detection for other fields
            if data.description is not None and data.description != existing['description']:
                updates.append("description = %s")
                params.append(data.description)
                has_changes = True
            
            if data.used_in_global_search is not None and data.used_in_global_search != existing['used_in_global_search']:
                updates.append("used_in_global_search = %s")
                params.append(data.used_in_global_search)
                has_changes = True
            
            if data.enable_audit is not None and data.enable_audit != existing['enable_audit']:
                updates.append("enable_audit = %s")
                params.append(data.enable_audit)
                has_changes = True
            
            if data.is_remote_object is not None and data.is_remote_object != existing['is_remote_object']:
                updates.append("is_remote_object = %s")
                params.append(data.is_remote_object)
                has_changes = True
            
            # For JSON fields, compare as strings to detect changes
            if data.fields is not None:
                import json
                new_fields_str = json.dumps(data.fields, sort_keys=True)
                old_fields_str = json.dumps(existing['fields'], sort_keys=True) if existing['fields'] else None
                if new_fields_str != old_fields_str:
                    updates.append("fields = %s")
                    params.append(psycopg2.extras.Json(data.fields))
                    has_changes = True
            
            if data.dependencies is not None:
                import json
                new_deps_str = json.dumps(data.dependencies, sort_keys=True) if data.dependencies else None
                old_deps_str = json.dumps(existing['dependencies'], sort_keys=True) if existing['dependencies'] else None
                if new_deps_str != old_deps_str:
                    updates.append("dependencies = %s")
                    params.append(psycopg2.extras.Json(data.dependencies) if data.dependencies else None)
                    has_changes = True
            
            if data.uniqueness is not None:
                import json
                new_uniq_str = json.dumps(data.uniqueness, sort_keys=True) if data.uniqueness else None
                old_uniq_str = json.dumps(existing['uniqueness'], sort_keys=True) if existing['uniqueness'] else None
                if new_uniq_str != old_uniq_str:
                    updates.append("uniqueness = %s")
                    params.append(psycopg2.extras.Json(data.uniqueness) if data.uniqueness else None)
                    has_changes = True
            
            if data.reference_controls is not None:
                import json
                new_rc_str = json.dumps(data.reference_controls, sort_keys=True) if data.reference_controls else None
                old_rc_str = json.dumps(existing['reference_controls'], sort_keys=True) if existing['reference_controls'] else None
                if new_rc_str != old_rc_str:
                    updates.append("reference_controls = %s")
                    params.append(psycopg2.extras.Json(data.reference_controls) if data.reference_controls else None)
                    has_changes = True
            
            if data.advanced_search is not None:
                import json
                new_as_str = json.dumps(data.advanced_search, sort_keys=True) if data.advanced_search else None
                old_as_str = json.dumps(existing['advanced_search'], sort_keys=True) if existing['advanced_search'] else None
                if new_as_str != old_as_str:
                    updates.append("advanced_search = %s")
                    params.append(psycopg2.extras.Json(data.advanced_search) if data.advanced_search else None)
                    has_changes = True
            
            if data.validation_rules is not None:
                import json
                new_vr_str = json.dumps(data.validation_rules, sort_keys=True) if data.validation_rules else None
                old_vr_str = json.dumps(existing['validation_rules'], sort_keys=True) if existing['validation_rules'] else None
                if new_vr_str != old_vr_str:
                    updates.append("validation_rules = %s")
                    params.append(psycopg2.extras.Json(data.validation_rules) if data.validation_rules else None)
                    has_changes = True
            
            if not has_changes:
                # No actual changes detected, return current record without update
                cur.close()
                logger.info(f"No changes detected for object {object_id} in {schema}")
                return self.get_by_id(object_id, user_role, customer_id)
            
            # If object was previously deployed (status='created'), set status to 'modified'
            # to indicate it needs redeployment to sync changes
            if existing['status'] == 'created':
                updates.append("status = %s")
                params.append('modified')
                logger.info(f"Object {object_id} status changed to 'modified' due to modifications")
            
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
