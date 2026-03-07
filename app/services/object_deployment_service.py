"""Service for deploying object metadata as database tables."""

import logging
import re
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2.extras
from psycopg2.extensions import ISOLATION_LEVEL_SERIALIZABLE

from app.db.connection import db_manager

logger = logging.getLogger(__name__)


class ObjectDeploymentService:
    """Service for deploying object metadata to database tables."""
    
    @staticmethod
    def _get_connection_and_schema(
        user_role: str, customer_id: Optional[str]
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
    
    @staticmethod
    def _get_object_prefix(api_name: str) -> str:
        """
        Extract prefix from object api_name.
        
        Example: abc12_work_order → abc12
        
        Args:
            api_name: Object api_name
            
        Returns:
            Prefix string
        """
        parts = api_name.split('_', 1)
        return parts[0] if len(parts) > 1 else api_name
    
    @staticmethod
    def _escape_sql_string(value: str) -> str:
        """Escape single quotes in SQL strings."""
        if not value:
            return ""
        return value.replace("'", "''")
    
    @staticmethod
    def _parse_date_default(value: str, is_datetime: bool) -> str:
        """
        Parse date default value like TODAY+5, TODAY-10.
        
        Args:
            value: Default value string
            is_datetime: True for datetime, False for date
            
        Returns:
            SQL default expression
        """
        if not value or str(value).lower() == 'null':
            return None
        
        # Match TODAY+N or TODAY-N pattern
        match = re.match(r'TODAY([+-]\d+)', str(value), re.IGNORECASE)
        if match:
            offset = int(match.group(1))
            base = "now()" if is_datetime else "now()::date"
            if offset == 0:
                return base
            else:
                return f"{base} + INTERVAL '{offset} days'"
        
        raise ValueError(f"Invalid date default value: {value}")
    
    def _load_datatype_mappings(
        self, schema: str, cursor
    ) -> Dict[str, str]:
        """
        Load datatype mappings from sys_om_datatype_mappings.
        
        Returns:
            Dict mapping om_datatype to db_datatype
        """
        cursor.execute(f"""
            SELECT om_datatype, db_datatype 
            FROM {schema}.sys_om_datatype_mappings
            ORDER BY om_datatype
        """)
        
        mappings = {row['om_datatype']: row['db_datatype'] for row in cursor.fetchall()}
        logger.info(f"Loaded {len(mappings)} datatype mappings")
        return mappings
    
    def _validate_fields(
        self, fields: List[Dict], schema: str, cursor
    ) -> None:
        """
        Validate fields array structure and values.
        
        Args:
            fields: Fields array from object metadata
            schema: Database schema
            cursor: Database cursor
            
        Raises:
            ValueError: If validation fails
        """
        if not fields:
            return  # Empty fields is valid
        
        # Check for duplicate api_names
        api_names = [f.get('api_name') for f in fields]
        if len(api_names) != len(set(api_names)):
            raise ValueError("Duplicate field api_names found")
        
        # Validate each field
        for idx, field in enumerate(fields):
            # Check required keys
            if 'api_name' not in field:
                raise ValueError(f"Field {idx}: Missing 'api_name'")
            if 'type' not in field:
                raise ValueError(f"Field {idx}: Missing 'type'")
            if 'label' not in field:
                raise ValueError(f"Field {idx}: Missing 'label'")
            
            # Validate api_name format
            api_name = field['api_name']
            if not re.match(r'^[a-z][a-z0-9_]*$', api_name):
                raise ValueError(
                    f"Field '{api_name}': Invalid format. "
                    f"Must start with lowercase letter and contain only a-z, 0-9, _"
                )
            
            # Validate Reference type has referenced_object
            if field['type'] == 'Reference':
                if 'referenced_object' not in field:
                    raise ValueError(
                        f"Field '{api_name}': Reference type requires 'referenced_object'"
                    )
                
                # Check referenced table exists
                ref_table = field['referenced_object']
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                    ) as exists
                """, (schema, ref_table))
                
                if not cursor.fetchone()['exists']:
                    raise ValueError(
                        f"Field '{api_name}': Referenced table '{ref_table}' does not exist. "
                        f"Deploy that object first."
                    )
            
            # Validate Picklist has values
            if field['type'] == 'Picklist':
                if not field.get('values') or not isinstance(field.get('values'), list):
                    raise ValueError(
                        f"Field '{api_name}': Picklist type requires non-empty 'values' array"
                    )
            
            # Validate Currency/Number has decimal_points
            if field['type'] in ['Currency', 'Number']:
                if 'decimal_points' not in field:
                    raise ValueError(
                        f"Field '{api_name}': {field['type']} type requires 'decimal_points'"
                    )
                decimals = field['decimal_points']
                if not isinstance(decimals, int) or decimals < 0 or decimals > 10:
                    raise ValueError(
                        f"Field '{api_name}': decimal_points must be integer 0-10"
                    )
            
            # Validate Text has length
            if field['type'] == 'Text':
                if 'length' not in field:
                    raise ValueError(
                        f"Field '{api_name}': Text type requires 'length'"
                    )
                length = field['length']
                if not isinstance(length, int) or length < 1 or length > 65535:
                    raise ValueError(
                        f"Field '{api_name}': length must be integer 1-65535"
                    )
    
    def _build_column_definition(
        self, field: Dict, object_prefix: str, datatype_mappings: Dict[str, str]
    ) -> str:
        """
        Build SQL column definition for a field.
        
        Args:
            field: Field definition
            object_prefix: Object prefix
            datatype_mappings: OM to DB datatype mappings
            
        Returns:
            SQL column definition string
        """
        column_name = f"{object_prefix}_{field['api_name']}"
        om_type = field['type']
        
        # Get base database type
        if om_type not in datatype_mappings:
            raise ValueError(f"Unknown datatype: {om_type}")
        
        db_type = datatype_mappings[om_type]
        
        # Apply type-specific modifiers
        if om_type in ['Currency', 'Number']:
            decimals = field.get('decimal_points', 2)
            db_type = f"NUMERIC({decimals},{decimals})"
        
        elif om_type == 'Text':
            length = field.get('length', 255)
            db_type = f"VARCHAR({length})"
        
        elif om_type == 'LongText':
            db_type = "TEXT"
        
        elif om_type == 'Email':
            db_type = "CITEXT"
        
        elif om_type == 'Phone':
            db_type = "VARCHAR(20)"
        
        elif om_type == 'Picklist':
            db_type = "TEXT[]"
        
        elif om_type in ['Picture', 'Video']:
            db_type = "TEXT"  # Store S3 URL
        
        elif om_type == 'Reference':
            db_type = "UUID"
        
        # Build NOT NULL constraint
        null_constraint = ""
        if field.get('required', False):
            null_constraint = " NOT NULL"
        
        # Build DEFAULT value
        default_value = ""
        if 'default_value' in field and field['default_value'] is not None:
            if om_type in ['Date', 'Datetime']:
                parsed = self._parse_date_default(
                    field['default_value'], 
                    om_type == 'Datetime'
                )
                if parsed:
                    default_value = f" DEFAULT {parsed}"
            elif om_type == 'Boolean':
                default_value = f" DEFAULT {str(field['default_value']).lower()}"
            elif om_type in ['Currency', 'Number']:
                default_value = f" DEFAULT {field['default_value']}"
        
        return f"{column_name} {db_type}{null_constraint}{default_value}"
    
    def _build_create_table_sql(
        self,
        schema: str,
        api_name: str,
        object_prefix: str,
        fields: List[Dict],
        datatype_mappings: Dict[str, str]
    ) -> str:
        """
        Build CREATE TABLE SQL statement.
        
        Args:
            schema: Database schema
            api_name: Table name
            object_prefix: Object prefix for field names
            fields: Field definitions
            datatype_mappings: Datatype mappings
            
        Returns:
            CREATE TABLE SQL statement
        """
        column_defs = []
        
        # System fields (no prefix)
        column_defs.append("id UUID PRIMARY KEY DEFAULT gen_random_uuid()")
        column_defs.append("created_by UUID NOT NULL")
        column_defs.append("modified_by UUID NOT NULL")
        column_defs.append("created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()")
        column_defs.append("modified_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()")
        column_defs.append("audit_info JSONB")
        
        # User-defined fields (with prefix)
        for field in fields:
            column_def = self._build_column_definition(
                field, object_prefix, datatype_mappings
            )
            column_defs.append(column_def)
        
        # Build CREATE TABLE statement
        columns_sql = ",\n    ".join(column_defs)
        
        sql = f"""CREATE TABLE IF NOT EXISTS {schema}.{api_name} (
    {columns_sql}
);"""
        
        return sql
    
    def _build_comment_statements(
        self,
        schema: str,
        api_name: str,
        object_prefix: str,
        description: Optional[str],
        fields: List[Dict]
    ) -> List[str]:
        """Build COMMENT ON statements for table and columns."""
        comments = []
        
        # Table comment
        if description:
            escaped_desc = self._escape_sql_string(description)
            comments.append(
                f"COMMENT ON TABLE {schema}.{api_name} IS '{escaped_desc}';"
            )
        
        # Column comments
        for field in fields:
            if field.get('description'):
                column_name = f"{object_prefix}_{field['api_name']}"
                escaped_desc = self._escape_sql_string(field['description'])
                comments.append(
                    f"COMMENT ON COLUMN {schema}.{api_name}.{column_name} "
                    f"IS '{escaped_desc}';"
                )
        
        return comments
    
    def _build_constraint_statements(
        self, schema: str, api_name: str, object_prefix: str, fields: List[Dict]
    ) -> List[str]:
        """Build ALTER TABLE statements for unique constraints."""
        constraints = []
        
        for field in fields:
            if field.get('unique', False):
                column_name = f"{object_prefix}_{field['api_name']}"
                constraint_name = f"unique_{column_name}"
                constraints.append(
                    f"ALTER TABLE {schema}.{api_name} "
                    f"ADD CONSTRAINT {constraint_name} UNIQUE ({column_name});"
                )
        
        return constraints
    
    def _build_foreign_key_statements(
        self, schema: str, api_name: str, object_prefix: str, fields: List[Dict]
    ) -> List[str]:
        """Build ALTER TABLE statements for foreign keys."""
        foreign_keys = []
        
        for field in fields:
            if field['type'] == 'Reference':
                column_name = f"{object_prefix}_{field['api_name']}"
                ref_table = field['referenced_object']
                fk_name = f"fk_{column_name}"
                
                foreign_keys.append(
                    f"ALTER TABLE {schema}.{api_name} "
                    f"ADD CONSTRAINT {fk_name} "
                    f"FOREIGN KEY ({column_name}) "
                    f"REFERENCES {schema}.{ref_table}(id) "
                    f"ON DELETE RESTRICT;"
                )
        
        return foreign_keys
    
    def _build_index_statements(
        self, schema: str, api_name: str, object_prefix: str, fields: List[Dict]
    ) -> List[str]:
        """Build CREATE INDEX statements."""
        indexes = []
        
        # Index on created_date (for sorting)
        indexes.append(
            f"CREATE INDEX idx_{api_name}_created_date "
            f"ON {schema}.{api_name}(created_date DESC);"
        )
        
        # Index on modified_date (for sorting)
        indexes.append(
            f"CREATE INDEX idx_{api_name}_modified_date "
            f"ON {schema}.{api_name}(modified_date DESC);"
        )
        
        # Indexes on user fields
        for field in fields:
            column_name = f"{object_prefix}_{field['api_name']}"
            
            # Index on unique fields
            if field.get('unique', False):
                indexes.append(
                    f"CREATE INDEX idx_{api_name}_{field['api_name']} "
                    f"ON {schema}.{api_name}({column_name});"
                )
            
            # Index on foreign keys
            if field['type'] == 'Reference':
                indexes.append(
                    f"CREATE INDEX idx_{api_name}_{field['api_name']} "
                    f"ON {schema}.{api_name}({column_name});"
                )
        
        return indexes
    
    def deploy_object(
        self,
        object_id: UUID,
        user_role: str,
        customer_id: Optional[str]
    ) -> Dict:
        """
        Deploy object metadata as database table.
        
        Args:
            object_id: Object metadata UUID
            user_role: User's role
            customer_id: Customer ID
            
        Returns:
            Deployment result dictionary
            
        Raises:
            ValueError: If validation fails
            Exception: If deployment fails
        """
        conn, schema, db_type = self._get_connection_and_schema(
            user_role, customer_id
        )
        
        try:
            # Set SERIALIZABLE isolation for strict consistency
            conn.set_isolation_level(ISOLATION_LEVEL_SERIALIZABLE)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Fetch object metadata
            cur.execute(f"""
                SELECT id, label, api_name, description, fields, status, created_by
                FROM {schema}.sys_object_metadata
                WHERE id = %s
            """, (str(object_id),))
            
            obj = cur.fetchone()
            if not obj:
                raise ValueError(f"Object {object_id} not found")
            
            # Validate status
            if obj['status'] not in ['draft', 'failed']:
                raise ValueError(
                    f"Cannot deploy object with status '{obj['status']}'. "
                    f"Only 'draft' or 'failed' objects can be deployed."
                )
            
            # Check if table already exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                ) as exists
            """, (schema, obj['api_name']))
            
            if cur.fetchone()['exists']:
                raise ValueError(
                    f"Table {schema}.{obj['api_name']} already exists"
                )
            
            # Extract data
            api_name = obj['api_name']
            object_prefix = self._get_object_prefix(api_name)
            fields = obj['fields'] or []
            description = obj['description']
            
            # Load datatype mappings
            datatype_mappings = self._load_datatype_mappings(schema, cur)
            
            # Validate fields
            self._validate_fields(fields, schema, cur)
            
            # Check if Email fields exist (need citext extension)
            has_email_fields = any(f['type'] == 'Email' for f in fields)
            
            # Update status to 'deploying'
            cur.execute(f"""
                UPDATE {schema}.sys_object_metadata
                SET status = 'deploying',
                    deployment_started_date = now(),
                    modified_date = now()
                WHERE id = %s
            """, (str(object_id),))
            
            logger.info(f"Starting deployment of {api_name} ({object_id})")
            
            # Install extensions if needed
            if has_email_fields:
                cur.execute("CREATE EXTENSION IF NOT EXISTS citext;")
                logger.info("Installed citext extension")
            
            # Build SQL statements
            create_table_sql = self._build_create_table_sql(
                schema, api_name, object_prefix, fields, datatype_mappings
            )
            
            comment_stmts = self._build_comment_statements(
                schema, api_name, object_prefix, description, fields
            )
            
            constraint_stmts = self._build_constraint_statements(
                schema, api_name, object_prefix, fields
            )
            
            fk_stmts = self._build_foreign_key_statements(
                schema, api_name, object_prefix, fields
            )
            
            index_stmts = self._build_index_statements(
                schema, api_name, object_prefix, fields
            )
            
            # Execute deployment
            logger.debug(f"CREATE TABLE SQL:\n{create_table_sql}")
            cur.execute(create_table_sql)
            
            for stmt in comment_stmts:
                cur.execute(stmt)
            
            for stmt in constraint_stmts:
                cur.execute(stmt)
            
            for stmt in fk_stmts:
                cur.execute(stmt)
            
            for stmt in index_stmts:
                cur.execute(stmt)
            
            # Verify table was actually created
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                ) as exists
            """, (schema, api_name))
            
            if not cur.fetchone()['exists']:
                raise ValueError(
                    f"Table {schema}.{api_name} was not created successfully"
                )
            
            logger.info(f"Verified table {schema}.{api_name} exists in database")
            
            # Update status to 'created'
            cur.execute(f"""
                UPDATE {schema}.sys_object_metadata
                SET status = 'created',
                    table_created_date = now(),
                    table_name = %s,
                    deployment_error = NULL,
                    modified_date = now()
                WHERE id = %s
                RETURNING deployment_started_date, table_created_date
            """, (api_name, str(object_id)))
            
            result = cur.fetchone()
            
            # Commit transaction
            conn.commit()
            cur.close()
            
            logger.info(
                f"Successfully deployed {api_name} with {len(fields)} fields"
            )
            
            return {
                "object_id": str(object_id),
                "api_name": api_name,
                "table_name": api_name,
                "schema": schema,
                "status": "created",
                "deployment_started_date": result['deployment_started_date'],
                "table_created_date": result['table_created_date'],
                "fields_deployed": len(fields),
                "message": "Table created successfully"
            }
            
        except Exception as e:
            # Rollback transaction
            conn.rollback()
            
            # Update status to 'failed' with error message
            try:
                cur = conn.cursor()
                cur.execute(f"""
                    UPDATE {schema}.sys_object_metadata
                    SET status = 'failed',
                        deployment_error = %s,
                        modified_date = now()
                    WHERE id = %s
                """, (str(e)[:1000], str(object_id)))  # Limit error message length
                conn.commit()
                cur.close()
            except Exception as update_error:
                logger.error(f"Failed to update error status: {update_error}")
            
            logger.error(f"Deployment failed for {object_id}: {e}")
            raise
            
        finally:
            if db_type == "core":
                db_manager.return_core_connection(conn)
            else:
                db_manager.return_tenants_connection(conn)
