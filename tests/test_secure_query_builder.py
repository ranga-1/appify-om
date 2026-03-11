"""Unit tests for SecureQueryBuilder class."""

import pytest
from uuid import UUID
from app.services.permissions.secure_query_builder import (
    SecureQueryBuilder,
    QueryFilter,
    FieldAccess,
    Scope
)


class TestSecureQueryBuilder:
    """Test suite for SecureQueryBuilder."""
    
    @pytest.fixture
    def user_id(self):
        """Test user ID."""
        return UUID("12345678-1234-1234-1234-123456789012")
    
    @pytest.fixture
    def basic_field_access(self):
        """Basic field access for testing."""
        return {
            "id": FieldAccess.READ,
            "name": FieldAccess.WRITE,
            "email": FieldAccess.WRITE,
            "salary": FieldAccess.MASK,
            "ssn": FieldAccess.HIDE,
        }
    
    # ========================================================================
    # build_select() Tests
    # ========================================================================
    
    def test_build_select_basic(self, user_id, basic_field_access):
        """Test basic SELECT query."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        sql, params = builder.build_select()
        
        assert "SELECT" in sql
        assert "FROM tenant_abc.abc12_employee" in sql
        assert "name" in sql
        assert "email" in sql
        assert "'***MASKED***' AS salary" in sql  # Masked field
        assert "ssn" not in sql  # Hidden field
    
    def test_build_select_with_scope_filter(self, user_id, basic_field_access):
        """Test SELECT with scope filtering."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.SELF,
            field_access=basic_field_access
        )
        
        sql, params = builder.build_select()
        
        assert "WHERE" in sql
        assert "created_by = :scope_user_id" in sql
        assert params["scope_user_id"] == str(user_id)
    
    def test_build_select_with_filters(self, user_id, basic_field_access):
        """Test SELECT with user-provided filters."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        filters = [
            QueryFilter("name", "like", "%John%"),
            QueryFilter("email", "eq", "john@example.com")
        ]
        
        sql, params = builder.build_select(filters=filters)
        
        assert "WHERE" in sql
        assert "name LIKE :f0_name" in sql
        assert "email = :f1_email" in sql
        assert params["f0_name"] == "%John%"
        assert params["f1_email"] == "john@example.com"
    
    def test_build_select_with_pagination(self, user_id, basic_field_access):
        """Test SELECT with pagination."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        sql, params = builder.build_select(limit=10, offset=20)
        
        assert "LIMIT :limit" in sql
        assert "OFFSET :offset" in sql
        assert params["limit"] == 10
        assert params["offset"] == 20
    
    def test_build_select_with_ordering(self, user_id, basic_field_access):
        """Test SELECT with ORDER BY."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        order_by = [("name", "ASC"), ("email", "DESC")]
        sql, params = builder.build_select(order_by=order_by)
        
        assert "ORDER BY name ASC, email DESC" in sql
    
    def test_build_select_permission_error_on_hidden_field_filter(self, user_id, basic_field_access):
        """Test that filtering on hidden field raises PermissionError."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        filters = [QueryFilter("ssn", "eq", "123-45-6789")]
        
        with pytest.raises(PermissionError, match="Cannot filter on field: ssn"):
            builder.build_select(filters=filters)
    
    def test_build_select_permission_error_on_hidden_field_order(self, user_id, basic_field_access):
        """Test that ordering by hidden field raises PermissionError."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        order_by = [("ssn", "ASC")]
        
        with pytest.raises(PermissionError, match="Cannot order by field: ssn"):
            builder.build_select(order_by=order_by)
    
    # ========================================================================
    # build_insert() Tests
    # ========================================================================
    
    def test_build_insert_basic(self, user_id, basic_field_access):
        """Test basic INSERT query."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        data = {"name": "John Doe", "email": "john@example.com"}
        sql, params = builder.build_insert(data)
        
        assert "INSERT INTO tenant_abc.abc12_employee" in sql
        assert "name" in sql
        assert "email" in sql
        assert "created_by" in sql
        assert "modified_by" in sql
        assert "RETURNING id" in sql
        assert params["name"] == "John Doe"
        assert params["email"] == "john@example.com"
        assert params["created_by"] == str(user_id)
        assert params["modified_by"] == str(user_id)
    
    def test_build_insert_permission_error_on_readonly_field(self, user_id, basic_field_access):
        """Test that writing to read-only field raises PermissionError."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        data = {"id": "fake-id"}  # id is READ-only
        
        with pytest.raises(PermissionError, match="Cannot write to field: id"):
            builder.build_insert(data)
    
    # ========================================================================
    # build_update() Tests
    # ========================================================================
    
    def test_build_update_basic(self, user_id, basic_field_access):
        """Test basic UPDATE query."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.SELF,
            field_access=basic_field_access
        )
        
        data = {"name": "Jane Doe"}
        filters = [QueryFilter("id", "eq", "some-uuid")]
        sql, params = builder.build_update(data, filters)
        
        assert "UPDATE tenant_abc.abc12_employee" in sql
        assert "SET name = :name" in sql
        assert "modified_by = :modified_by" in sql
        assert "WHERE" in sql
        assert "created_by = :scope_user_id" in sql  # Scope filter
        assert "id = :f0_id" in sql  # User filter
        assert "RETURNING id" in sql
        assert params["name"] == "Jane Doe"
        assert params["modified_by"] == str(user_id)
    
    def test_build_update_requires_filter(self, user_id, basic_field_access):
        """Test that UPDATE without filter raises ValueError."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,  # No scope filter
            field_access=basic_field_access
        )
        
        data = {"name": "Jane Doe"}
        
        with pytest.raises(ValueError, match="UPDATE requires at least one filter condition"):
            builder.build_update(data, filters=None)
    
    # ========================================================================
    # build_delete() Tests
    # ========================================================================
    
    def test_build_delete_basic(self, user_id, basic_field_access):
        """Test basic DELETE query."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.SELF,
            field_access=basic_field_access
        )
        
        filters = [QueryFilter("id", "eq", "some-uuid")]
        sql, params = builder.build_delete(filters)
        
        assert "DELETE FROM tenant_abc.abc12_employee" in sql
        assert "WHERE" in sql
        assert "created_by = :scope_user_id" in sql  # Scope filter
        assert "id = :f0_id" in sql  # User filter
        assert "RETURNING id" in sql
    
    def test_build_delete_requires_filter(self, user_id, basic_field_access):
        """Test that DELETE without filter raises ValueError."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,  # No scope filter
            field_access=basic_field_access
        )
        
        with pytest.raises(ValueError, match="DELETE requires at least one filter condition"):
            builder.build_delete(filters=None)
    
    # ========================================================================
    # build_count() Tests
    # ========================================================================
    
    def test_build_count_basic(self, user_id, basic_field_access):
        """Test basic COUNT query."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        sql, params = builder.build_count()
        
        assert "SELECT COUNT(*) as count FROM tenant_abc.abc12_employee" in sql
    
    def test_build_count_with_filters(self, user_id, basic_field_access):
        """Test COUNT with filters."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        filters = [QueryFilter("name", "like", "%John%")]
        sql, params = builder.build_count(filters)
        
        assert "WHERE name LIKE :f0_name" in sql
        assert params["f0_name"] == "%John%"
    
    # ========================================================================
    # Query Filter Operators Tests
    # ========================================================================
    
    def test_query_filter_in_operator(self, user_id, basic_field_access):
        """Test IN operator."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        filters = [QueryFilter("name", "in", ["John", "Jane", "Bob"])]
        sql, params = builder.build_select(filters=filters)
        
        assert "name = ANY(:f0_name)" in sql
        assert params["f0_name"] == ["John", "Jane", "Bob"]
    
    def test_query_filter_between_operator(self, user_id, basic_field_access):
        """Test BETWEEN operator."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        filters = [QueryFilter("salary", "between", [50000, 100000])]
        sql, params = builder.build_count(filters=filters)
        
        assert "salary BETWEEN :f0_salary_min AND :f0_salary_max" in sql
        assert params["f0_salary_min"] == 50000
        assert params["f0_salary_max"] == 100000
    
    def test_query_filter_is_null_operator(self, user_id, basic_field_access):
        """Test IS NULL operator."""
        builder = SecureQueryBuilder(
            schema_name="tenant_abc",
            table_name="abc12_employee",
            user_id=user_id,
            scope=Scope.ALL,
            field_access=basic_field_access
        )
        
        filters = [QueryFilter("email", "is_null", None)]
        sql, params = builder.build_count(filters=filters)
        
        assert "email IS NULL" in sql
    
    def test_query_filter_invalid_operator(self):
        """Test invalid operator raises ValueError."""
        with pytest.raises(ValueError, match="Invalid operator: invalid"):
            QueryFilter("name", "invalid", "value")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
