"""Secure SQL query builder with automatic permission enforcement."""

from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from sqlalchemy import text, and_, or_
from sqlalchemy.sql import Select, Insert, Update, Delete

from .permission_checker import PermissionChecker, Scope, FieldAccess


class QueryFilter:
    """Represents a query filter condition."""
    
    def __init__(self, field: str, operator: str, value: Any):
        """
        Initialize a query filter.
        
        Args:
            field: Field name to filter on
            operator: Operator (eq, ne, gt, lt, gte, lte, in, like, between)
            value: Value to compare against
        """
        self.field = field
        self.operator = operator
        self.value = value
        
        # Validate operator
        allowed_operators = {"eq", "ne", "gt", "lt", "gte", "lte", "in", "like", "between", "is_null", "is_not_null"}
        if operator not in allowed_operators:
            raise ValueError(f"Invalid operator: {operator}. Allowed: {allowed_operators}")


class SecureQueryBuilder:
    """
    Builds SQL queries with automatic permission-based filtering.
    
    Security Features:
    - Parameterized queries (SQL injection prevention)
    - Automatic row-level filtering based on scope
    - Field-level filtering (read/write/mask/hide)
    - Audit trail injection (created_by, modified_by)
    """
    
    def __init__(
        self,
        schema_name: str,
        table_name: str,
        user_id: UUID,
        scope: Scope,
        field_access: Dict[str, FieldAccess]
    ):
        """
        Initialize query builder.
        
        Args:
            schema_name: Database schema name (e.g., "tenant_abc")
            table_name: Table name (e.g., "abc12_customer")
            user_id: Current user's UUID
            scope: Data access scope
            field_access: Dictionary of field name to access level
        """
        self.schema_name = schema_name
        self.table_name = table_name
        self.user_id = user_id
        self.scope = scope
        self.field_access = field_access
        self.full_table_name = f"{schema_name}.{table_name}"
    
    def build_select(
        self,
        filters: Optional[List[QueryFilter]] = None,
        order_by: Optional[List[Tuple[str, str]]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build SELECT query with permission enforcement.
        
        Args:
            filters: List of QueryFilter objects
            order_by: List of (field, direction) tuples
            limit: Maximum records to return
            offset: Number of records to skip
            
        Returns:
            Tuple of (SQL string, parameters dict)
            
        Raises:
            PermissionError: If trying to access hidden fields
        """
        # Get readable fields
        readable_fields = self._get_readable_fields()
        if not readable_fields:
            raise PermissionError("No readable fields available")
        
        # Build field list with masking
        select_fields = []
        for field in readable_fields:
            access = self.field_access.get(field, FieldAccess.HIDE)
            if access == FieldAccess.MASK:
                # Mask sensitive fields
                select_fields.append(f"'***MASKED***' AS {field}")
            else:
                select_fields.append(field)
        
        # Always include ID if available
        if "id" not in readable_fields:
            select_fields.insert(0, "id")
        
        field_list = ", ".join(select_fields)
        
        # Build WHERE clause with scope filter
        where_clauses = []
        params = {}
        
        # Add scope filter
        scope_clause, scope_params = self._build_scope_filter()
        if scope_clause:
            where_clauses.append(scope_clause)
            params.update(scope_params)
        
        # Add user filters
        if filters:
            for i, filter_obj in enumerate(filters):
                if not self._can_read_field(filter_obj.field):
                    raise PermissionError(f"Cannot filter on field: {filter_obj.field}")
                
                clause, filter_params = self._build_filter_clause(filter_obj, f"f{i}")
                where_clauses.append(clause)
                params.update(filter_params)
        
        # Build full SQL
        sql_parts = [f"SELECT {field_list} FROM {self.full_table_name}"]
        
        if where_clauses:
            sql_parts.append(f"WHERE {' AND '.join(where_clauses)}")
        
        # Add ORDER BY
        if order_by:
            order_clauses = []
            for field, direction in order_by:
                if not self._can_read_field(field):
                    raise PermissionError(f"Cannot order by field: {field}")
                direction_upper = direction.upper()
                if direction_upper not in ("ASC", "DESC"):
                    raise ValueError(f"Invalid order direction: {direction}")
                order_clauses.append(f"{field} {direction_upper}")
            sql_parts.append(f"ORDER BY {', '.join(order_clauses)}")
        
        # Add LIMIT/OFFSET
        if limit is not None:
            sql_parts.append(f"LIMIT :limit")
            params["limit"] = limit
        
        if offset is not None:
            sql_parts.append(f"OFFSET :offset")
            params["offset"] = offset
        
        return " ".join(sql_parts), params
    
    def build_insert(
        self,
        data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build INSERT query with permission enforcement.
        
        Args:
            data: Dictionary of field name to value
            
        Returns:
            Tuple of (SQL string, parameters dict)
            
        Raises:
            PermissionError: If trying to write to read-only fields
        """
        # Filter to writable fields only
        writable_data = {}
        for field, value in data.items():
            if self._can_write_field(field):
                writable_data[field] = value
            else:
                raise PermissionError(f"Cannot write to field: {field}")
        
        if not writable_data:
            raise PermissionError("No writable fields in data")
        
        # Add audit fields
        writable_data["created_by"] = str(self.user_id)
        writable_data["modified_by"] = str(self.user_id)
        
        # Build INSERT
        fields = list(writable_data.keys())
        placeholders = [f":{field}" for field in fields]
        
        sql = f"""
            INSERT INTO {self.full_table_name} 
            ({', '.join(fields)}) 
            VALUES ({', '.join(placeholders)})
            RETURNING id
        """
        
        return sql.strip(), writable_data
    
    def build_update(
        self,
        data: Dict[str, Any],
        filters: Optional[List[QueryFilter]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build UPDATE query with permission enforcement.
        
        Args:
            data: Dictionary of field name to new value
            filters: List of QueryFilter objects for WHERE clause
            
        Returns:
            Tuple of (SQL string, parameters dict)
            
        Raises:
            PermissionError: If trying to write to read-only fields or update out-of-scope records
        """
        # Filter to writable fields only
        writable_data = {}
        for field, value in data.items():
            if self._can_write_field(field):
                writable_data[field] = value
            else:
                raise PermissionError(f"Cannot write to field: {field}")
        
        if not writable_data:
            raise PermissionError("No writable fields in data")
        
        # Add modified_by
        writable_data["modified_by"] = str(self.user_id)
        
        # Build SET clause
        set_clauses = [f"{field} = :{field}" for field in writable_data.keys()]
        
        # Build WHERE clause with scope filter
        where_clauses = []
        params = dict(writable_data)
        
        # Add scope filter (CRITICAL: prevents updating out-of-scope records)
        scope_clause, scope_params = self._build_scope_filter()
        if scope_clause:
            where_clauses.append(scope_clause)
            params.update(scope_params)
        
        # Add user filters
        if filters:
            for i, filter_obj in enumerate(filters):
                if not self._can_read_field(filter_obj.field):
                    raise PermissionError(f"Cannot filter on field: {filter_obj.field}")
                
                clause, filter_params = self._build_filter_clause(filter_obj, f"f{i}")
                where_clauses.append(clause)
                params.update(filter_params)
        
        if not where_clauses:
            raise ValueError("UPDATE requires at least one filter condition")
        
        sql = f"""
            UPDATE {self.full_table_name}
            SET {', '.join(set_clauses)}
            WHERE {' AND '.join(where_clauses)}
            RETURNING id
        """
        
        return sql.strip(), params
    
    def build_delete(
        self,
        filters: Optional[List[QueryFilter]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build DELETE query with permission enforcement.
        
        Args:
            filters: List of QueryFilter objects for WHERE clause
            
        Returns:
            Tuple of (SQL string, parameters dict)
            
        Raises:
            PermissionError: If trying to delete out-of-scope records
        """
        # Build WHERE clause with scope filter
        where_clauses = []
        params = {}
        
        # Add scope filter (CRITICAL: prevents deleting out-of-scope records)
        scope_clause, scope_params = self._build_scope_filter()
        if scope_clause:
            where_clauses.append(scope_clause)
            params.update(scope_params)
        
        # Add user filters
        if filters:
            for i, filter_obj in enumerate(filters):
                if not self._can_read_field(filter_obj.field):
                    raise PermissionError(f"Cannot filter on field: {filter_obj.field}")
                
                clause, filter_params = self._build_filter_clause(filter_obj, f"f{i}")
                where_clauses.append(clause)
                params.update(filter_params)
        
        if not where_clauses:
            raise ValueError("DELETE requires at least one filter condition")
        
        sql = f"""
            DELETE FROM {self.full_table_name}
            WHERE {' AND '.join(where_clauses)}
            RETURNING id
        """
        
        return sql.strip(), params
    
    def build_count(
        self,
        filters: Optional[List[QueryFilter]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build COUNT query with permission enforcement.
        
        Args:
            filters: List of QueryFilter objects
            
        Returns:
            Tuple of (SQL string, parameters dict)
        """
        where_clauses = []
        params = {}
        
        # Add scope filter
        scope_clause, scope_params = self._build_scope_filter()
        if scope_clause:
            where_clauses.append(scope_clause)
            params.update(scope_params)
        
        # Add user filters
        if filters:
            for i, filter_obj in enumerate(filters):
                if not self._can_read_field(filter_obj.field):
                    raise PermissionError(f"Cannot filter on field: {filter_obj.field}")
                
                clause, filter_params = self._build_filter_clause(filter_obj, f"f{i}")
                where_clauses.append(clause)
                params.update(filter_params)
        
        sql_parts = [f"SELECT COUNT(*) as count FROM {self.full_table_name}"]
        
        if where_clauses:
            sql_parts.append(f"WHERE {' AND '.join(where_clauses)}")
        
        return " ".join(sql_parts), params
    
    def build_aggregate(
        self,
        aggregations: List[Dict[str, Any]],
        group_by: Optional[List[str]] = None,
        filters: Optional[List[QueryFilter]] = None,
        having: Optional[List[QueryFilter]] = None,
        order_by: Optional[List[Tuple[str, str]]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build aggregate query with GROUP BY and HAVING.
        
        Args:
            aggregations: List of aggregation specs, each with 'field', 'function', 'alias'
            group_by: List of field names to group by
            filters: List of QueryFilter objects for WHERE clause
            having: List of QueryFilter objects for HAVING clause
            order_by: List of (field, direction) tuples
            limit: Maximum records to return
            offset: Number of records to skip
            
        Returns:
            Tuple of (SQL string, parameters dict)
            
        Example aggregations:
            [
                {"field": "*", "function": "count", "alias": "total_count"},
                {"field": "salary", "function": "avg", "alias": "avg_salary"},
                {"field": "salary", "function": "sum", "alias": "total_salary"}
            ]
        """
        params = {}
        select_parts = []
        
        # Add GROUP BY fields to SELECT
        if group_by:
            for field in group_by:
                if not self._can_read_field(field):
                    raise PermissionError(f"Cannot group by field: {field}")
                select_parts.append(field)
        
        # Add aggregation functions to SELECT
        allowed_functions = {"count", "sum", "avg", "min", "max", "count_distinct"}
        for agg in aggregations:
            function = agg["function"].lower()
            field = agg["field"]
            alias = agg.get("alias", f"{function}_{field}")
            
            if function not in allowed_functions:
                raise ValueError(f"Invalid aggregation function: {function}. Allowed: {allowed_functions}")
            
            # COUNT(*) doesn't need field permission check
            if field != "*" and not self._can_read_field(field):
                raise PermissionError(f"Cannot aggregate field: {field}")
            
            if function == "count_distinct":
                select_parts.append(f"COUNT(DISTINCT {field}) AS {alias}")
            elif function == "count" and field == "*":
                select_parts.append(f"COUNT(*) AS {alias}")
            else:
                select_parts.append(f"{function.upper()}({field}) AS {alias}")
        
        # Build WHERE clause with scope filter
        where_clauses = []
        
        # Add scope filter
        scope_clause, scope_params = self._build_scope_filter()
        if scope_clause:
            where_clauses.append(scope_clause)
            params.update(scope_params)
        
        # Add user filters
        if filters:
            for i, filter_obj in enumerate(filters):
                if not self._can_read_field(filter_obj.field):
                    raise PermissionError(f"Cannot filter on field: {filter_obj.field}")
                
                clause, filter_params = self._build_filter_clause(filter_obj, f"f{i}")
                where_clauses.append(clause)
                params.update(filter_params)
        
        # Build SQL
        sql_parts = [f"SELECT {', '.join(select_parts)} FROM {self.full_table_name}"]
        
        if where_clauses:
            sql_parts.append(f"WHERE {' AND '.join(where_clauses)}")
        
        # Add GROUP BY
        if group_by:
            sql_parts.append(f"GROUP BY {', '.join(group_by)}")
        
        # Add HAVING
        if having:
            having_clauses = []
            for i, filter_obj in enumerate(having):
                # HAVING operates on aggregated/grouped fields, so we don't check field permissions
                clause, filter_params = self._build_filter_clause(filter_obj, f"h{i}")
                having_clauses.append(clause)
                params.update(filter_params)
            sql_parts.append(f"HAVING {' AND '.join(having_clauses)}")
        
        # Add ORDER BY
        if order_by:
            order_clauses = []
            for field, direction in order_by:
                direction_upper = direction.upper()
                if direction_upper not in ("ASC", "DESC"):
                    raise ValueError(f"Invalid order direction: {direction}")
                order_clauses.append(f"{field} {direction_upper}")
            sql_parts.append(f"ORDER BY {', '.join(order_clauses)}")
        
        # Add LIMIT/OFFSET
        if limit is not None:
            sql_parts.append(f"LIMIT {limit}")
        if offset is not None:
            sql_parts.append(f"OFFSET {offset}")
        
        return " ".join(sql_parts), params
    
    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    def _build_scope_filter(self) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Build WHERE clause for scope-based row filtering.
        
        Returns:
            Tuple of (WHERE clause, parameters)
        """
        if self.scope == Scope.ALL:
            return None, {}
        
        if self.scope == Scope.SELF:
            return "created_by = :scope_user_id", {"scope_user_id": str(self.user_id)}
        
        if self.scope == Scope.TEAM:
            # Assumes table has team_id field
            # TODO: Make this configurable per object
            return "team_id = (SELECT team_id FROM sys_users WHERE id = :scope_user_id)", {
                "scope_user_id": str(self.user_id)
            }
        
        if self.scope == Scope.DEPARTMENT:
            # Assumes table has department_id field
            return "department_id = (SELECT department_id FROM sys_users WHERE id = :scope_user_id)", {
                "scope_user_id": str(self.user_id)
            }
        
        # Scope.NONE - no access
        return "1 = 0", {}  # Always false
    
    def _build_filter_clause(
        self,
        filter_obj: QueryFilter,
        param_prefix: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build WHERE clause for a single filter.
        
        Args:
            filter_obj: QueryFilter object
            param_prefix: Prefix for parameter names (for uniqueness)
            
        Returns:
            Tuple of (WHERE clause, parameters)
        """
        field = filter_obj.field
        operator = filter_obj.operator
        value = filter_obj.value
        
        param_name = f"{param_prefix}_{field}"
        
        if operator == "eq":
            return f"{field} = :{param_name}", {param_name: value}
        
        if operator == "ne":
            return f"{field} != :{param_name}", {param_name: value}
        
        if operator == "gt":
            return f"{field} > :{param_name}", {param_name: value}
        
        if operator == "lt":
            return f"{field} < :{param_name}", {param_name: value}
        
        if operator == "gte":
            return f"{field} >= :{param_name}", {param_name: value}
        
        if operator == "lte":
            return f"{field} <= :{param_name}", {param_name: value}
        
        if operator == "in":
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"'in' operator requires list/tuple value")
            # Use ANY for PostgreSQL array comparison
            return f"{field} = ANY(:{param_name})", {param_name: value}
        
        if operator == "like":
            return f"{field} LIKE :{param_name}", {param_name: value}
        
        if operator == "between":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError(f"'between' operator requires [min, max] value")
            return f"{field} BETWEEN :{param_name}_min AND :{param_name}_max", {
                f"{param_name}_min": value[0],
                f"{param_name}_max": value[1]
            }
        
        if operator == "is_null":
            return f"{field} IS NULL", {}
        
        if operator == "is_not_null":
            return f"{field} IS NOT NULL", {}
        
        raise ValueError(f"Unsupported operator: {operator}")
    
    def _get_readable_fields(self) -> List[str]:
        """Get list of fields user can read."""
        return [
            field for field, access in self.field_access.items()
            if access in (FieldAccess.READ, FieldAccess.WRITE, FieldAccess.MASK)
        ]
    
    def _can_read_field(self, field: str) -> bool:
        """Check if user can read a field."""
        access = self.field_access.get(field, FieldAccess.HIDE)
        return access in (FieldAccess.READ, FieldAccess.WRITE, FieldAccess.MASK)
    
    def _can_write_field(self, field: str) -> bool:
        """Check if user can write to a field."""
        access = self.field_access.get(field, FieldAccess.HIDE)
        return access == FieldAccess.WRITE
