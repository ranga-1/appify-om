"""Integration tests for Generic Data API endpoints.

NOTE: These are integration tests that require full database setup.
For now, they serve as API structure validation and documentation.
"""

import pytest
from uuid import uuid4

from app.models.data_api import (
    CreateRecordRequest,
    UpdateRecordRequest,
    QueryRecordsRequest,
    QueryFilter,
    RecordResponse,
    QueryRecordsResponse,
    BulkOperationResponse,
    ErrorResponse
)


class TestDataAPISchemas:
    """Test API request/response schemas."""
    
    def test_create_record_request_schema(self):
        """Test CreateRecordRequest schema validation."""
        # Valid request
        request = CreateRecordRequest(
            object_name="employee",
            data={"name": "John Doe", "email": "john@example.com"}
        )
        
        assert request.object_name == "employee"
        assert request.data["name"] == "John Doe"
    
    def test_query_filter_schema_validation(self):
        """Test QueryFilter validates operators."""
        # Valid operators
        for op in ["eq", "ne", "gt", "lt", "gte", "lte", "like", "in", "between", "is_null"]:
            filter_obj = QueryFilter(field="name", operator=op, value="test")
            assert filter_obj.operator == op
        
        # Invalid operator
        with pytest.raises(ValueError, match="Invalid operator"):
            QueryFilter(field="name", operator="invalid", value="test")
    
    def test_query_records_request_schema(self):
        """Test QueryRecordsRequest schema with defaults."""
        # Minimal request
        request = QueryRecordsRequest(object_name="employee")
        
        assert request.object_name == "employee"
        assert request.limit == 100  # Default
        assert request.offset == 0   # Default
        assert request.filters is None
        assert request.order_by is None
    
    def test_query_records_request_limit_validation(self):
        """Test QueryRecordsRequest validates limit bounds."""
        # Limit too high
        with pytest.raises(ValueError):
            QueryRecordsRequest(object_name="employee", limit=2000)
        
        # Limit too low
        with pytest.raises(ValueError):
            QueryRecordsRequest(object_name="employee", limit=0)
    
    def test_query_records_response_structure(self):
        """Test QueryRecordsResponse has correct fields."""
        from datetime import datetime
        
        response = QueryRecordsResponse(
            records=[],
            total=0,
            limit=50,
            offset=0,
            has_more=False
        )
        
        assert response.records == []
        assert response.total == 0
        assert response.has_more is False


class TestDataAPIEndpointStructure:
    """Test that API endpoints are properly configured."""
    
    def test_data_router_exists(self):
        """Test that data router is loaded."""
        from app.api.v1 import data
        
        assert data.router is not None
        assert data.router.prefix == "/data"
    
    def test_endpoints_have_correct_methods(self):
        """Test that endpoints have correct HTTP methods."""
        from app.api.v1 import data
        
        # Get all routes from router
        routes = {route.path: route for route in data.router.routes}
        
        # Check CREATE endpoint exists (includes /data prefix from router)
        assert "/data/records" in routes
        
        # Check GET endpoint exists
        assert "/data/records/{record_id}" in routes
        
        # Check QUERY endpoint exists
        assert "/data/query" in routes
    
    def test_permission_dependencies_exist(self):
        """Test that permission checking functions are available."""
        from app.api.v1.data import get_current_user, get_tenant_schema
        
        assert callable(get_current_user)
        assert callable(get_tenant_schema)


class TestPermissionIntegration:
    """Test permission system integration."""
    
    def test_permission_checker_available(self):
        """Test PermissionChecker is available for use."""
        from app.services.permissions.permission_checker import PermissionChecker
        
        permissions = ["data:read:*", "field:write:employee.name"]
        
        # Test has_permission
        assert PermissionChecker.has_permission(permissions, "data:read:employee")
        
        # Test get_data_scope
        scope = PermissionChecker.get_data_scope(permissions, "read")
        assert scope is not None
    
    def test_secure_query_builder_available(self):
        """Test SecureQueryBuilder is available for use."""
        from app.services.permissions.secure_query_builder import SecureQueryBuilder, FieldAccess, Scope
        from uuid import uuid4
        
        # Create builder instance
        builder = SecureQueryBuilder(
            schema_name="tenant_test",
            table_name="test_employee",
            user_id=uuid4(),
            scope=Scope.ALL,
            field_access={"name": FieldAccess.WRITE}
        )
        
        assert builder is not None
        assert builder.table_name == "test_employee"
    
    def test_permission_service_available(self):
        """Test PermissionService is available for use."""
        from app.services.permissions.permission_service import get_permission_service
        
        assert callable(get_permission_service)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
