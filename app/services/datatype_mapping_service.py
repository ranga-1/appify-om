"""Service layer for Datatype Mappings."""

import logging
from typing import List, Tuple

import psycopg2.extras

from app.db.connection import db_manager
from app.models.datatype_mapping import DatatypeMappingResponse

logger = logging.getLogger(__name__)


class DatatypeMappingService:
    """Service for managing datatype mappings (read-only)."""
    
    def _get_connection_and_schema(
        self, user_role: str, customer_id: str | None
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
        customer_id: str | None
    ) -> List[DatatypeMappingResponse]:
        """
        Get all datatype mappings.
        
        Args:
            user_role: User's role
            customer_id: Customer ID
            
        Returns:
            List of datatype mappings
        """
        conn, schema, db_type = self._get_connection_and_schema(
            user_role, customer_id
        )
        
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            query = f"""
                SELECT db_datatype, om_datatype, properties
                FROM {schema}.sys_om_datatype_mappings
                ORDER BY om_datatype
            """
            cur.execute(query)
            rows = cur.fetchall()
            
            items = [DatatypeMappingResponse(**row) for row in rows]
            
            cur.close()
            logger.info(
                f"Retrieved {len(items)} datatype mappings from {schema}"
            )
            return items
            
        finally:
            if db_type == "core":
                db_manager.return_core_connection(conn)
            else:
                db_manager.return_tenants_connection(conn)
