"""Tests for Phase 3 features: bulk operations, aggregations, export/import."""

import pytest
from app.models.data_api import (
    BulkCreateRequest,
    BulkUpdateRequest,
    BulkDeleteRequest,
    AggregationField,
    AggregateQueryRequest,
    ExportRequest,
    ImportRequest,
    QueryFilter
)


# ============================================================================
# Bulk Operations Schema Tests
# ============================================================================

class TestBulkOperationsSchemas:
    """Test bulk operation request/response schemas."""
    
    def test_bulk_create_request_schema(self):
        """Test bulk create request schema validation."""
        request = BulkCreateRequest(
            object_name="employee",
            records=[
                {"name": "John Doe", "email": "john@example.com"},
                {"name": "Jane Smith", "email": "jane@example.com"}
            ]
        )
        assert request.object_name == "employee"
        assert len(request.records) == 2
    
    def test_bulk_create_request_max_records(self):
        """Test bulk create rejects more than 1000 records."""
        with pytest.raises(ValueError, match="Cannot create more than 1000 records"):
            BulkCreateRequest(
                object_name="employee",
                records=[{"id": i} for i in range(1001)]
            )
    
    def test_bulk_create_request_empty_records(self):
        """Test bulk create requires at least one record."""
        with pytest.raises(ValueError, match="Must provide at least one record"):
            BulkCreateRequest(
                object_name="employee",
                records=[]
            )
    
    def test_bulk_update_request_schema(self):
        """Test bulk update request schema."""
        request = BulkUpdateRequest(
            object_name="employee",
            filters=[QueryFilter(field="department", operator="eq", value="Engineering")],
            data={"salary": 100000}
        )
        assert request.object_name == "employee"
        assert len(request.filters) == 1
        assert request.data == {"salary": 100000}
    
    def test_bulk_delete_request_schema(self):
        """Test bulk delete request schema."""
        request = BulkDeleteRequest(
            object_name="employee",
            filters=[QueryFilter(field="status", operator="eq", value="inactive")]
        )
        assert request.object_name == "employee"
        assert len(request.filters) == 1


# ============================================================================
# Aggregation Tests
# ============================================================================

class TestAggregationSchemas:
    """Test aggregation query schemas."""
    
    def test_aggregation_field_schema(self):
        """Test aggregation field schema."""
        agg = AggregationField(
            field="salary",
            function="avg",
            alias="avg_salary"
        )
        assert agg.field == "salary"
        assert agg.function == "avg"
        assert agg.alias == "avg_salary"
    
    def test_aggregation_field_invalid_function(self):
        """Test aggregation field rejects invalid function."""
        with pytest.raises(ValueError, match="Invalid function"):
            AggregationField(
                field="salary",
                function="invalid_func"
            )
    
    def test_aggregation_field_valid_functions(self):
        """Test all valid aggregation functions."""
        valid_functions = ["count", "sum", "avg", "min", "max", "count_distinct"]
        for func in valid_functions:
            agg = AggregationField(field="salary", function=func)
            assert agg.function == func.lower()
    
    def test_aggregate_query_request_schema(self):
        """Test aggregate query request schema."""
        request = AggregateQueryRequest(
            object_name="employee",
            aggregations=[
                AggregationField(field="*", function="count", alias="total"),
                AggregationField(field="salary", function="avg", alias="avg_salary")
            ],
            group_by=["department"],
            filters=[QueryFilter(field="status", operator="eq", value="active")]
        )
        assert request.object_name == "employee"
        assert len(request.aggregations) == 2
        assert request.group_by == ["department"]
        assert len(request.filters) == 1
    
    def test_aggregate_query_with_having(self):
        """Test aggregate query with HAVING clause."""
        request = AggregateQueryRequest(
            object_name="employee",
            aggregations=[
                AggregationField(field="*", function="count", alias="employee_count")
            ],
            group_by=["department"],
            having=[QueryFilter(field="employee_count", operator="gt", value=10)]
        )
        assert request.having is not None
        assert len(request.having) == 1


# ============================================================================
# Export Tests
# ============================================================================

class TestExportSchemas:
    """Test export request/response schemas."""
    
    def test_export_request_csv(self):
        """Test export request for CSV format."""
        request = ExportRequest(
            object_name="employee",
            format="csv",
            fields=["name", "email", "department"]
        )
        assert request.object_name == "employee"
        assert request.format == "csv"
        assert len(request.fields) == 3
    
    def test_export_request_json(self):
        """Test export request for JSON format."""
        request = ExportRequest(
            object_name="employee",
            format="json"
        )
        assert request.format == "json"
    
    def test_export_request_excel(self):
        """Test export request for Excel format."""
        request = ExportRequest(
            object_name="employee",
            format="excel"
        )
        assert request.format == "excel"
    
    def test_export_request_invalid_format(self):
        """Test export request rejects invalid format."""
        with pytest.raises(ValueError, match="Invalid format"):
            ExportRequest(
                object_name="employee",
                format="pdf"
            )
    
    def test_export_request_with_filters(self):
        """Test export request with filters."""
        request = ExportRequest(
            object_name="employee",
            format="csv",
            filters=[QueryFilter(field="department", operator="eq", value="Engineering")],
            limit=5000
        )
        assert len(request.filters) == 1
        assert request.limit == 5000


# ============================================================================
# Import Tests
# ============================================================================

class TestImportSchemas:
    """Test import request/response schemas."""
    
    def test_import_request_csv(self):
        """Test import request for CSV format."""
        request = ImportRequest(
            object_name="employee",
            format="csv",
            data="base64encodeddata",
            mode="insert"
        )
        assert request.object_name == "employee"
        assert request.format == "csv"
        assert request.mode == "insert"
    
    def test_import_request_json(self):
        """Test import request for JSON format."""
        request = ImportRequest(
            object_name="employee",
            format="json",
            data="base64encodeddata",
            mode="upsert",
            upsert_key=["email"]
        )
        assert request.format == "json"
        assert request.mode == "upsert"
        assert request.upsert_key == ["email"]
    
    def test_import_request_invalid_format(self):
        """Test import request rejects invalid format."""
        with pytest.raises(ValueError, match="Invalid format"):
            ImportRequest(
                object_name="employee",
                format="xml",
                data="data"
            )
    
    def test_import_request_invalid_mode(self):
        """Test import request rejects invalid mode."""
        with pytest.raises(ValueError, match="Invalid mode"):
            ImportRequest(
                object_name="employee",
                format="csv",
                data="data",
                mode="invalid_mode"
            )
    
    def test_import_request_validate_only(self):
        """Test import request with validate_only flag."""
        request = ImportRequest(
            object_name="employee",
            format="csv",
            data="data",
            mode="insert",
            validate_only=True
        )
        assert request.validate_only is True


# ============================================================================
# Integration Tests - Endpoint Structure
# ============================================================================

class TestPhase3EndpointStructure:
    """Test that Phase 3 endpoints are properly defined."""
    
    def test_bulk_create_endpoint_exists(self):
        """Test bulk create endpoint is registered."""
        from app.api.v1.data import router
        
        routes = {route.path: route for route in router.routes}
        assert "/data/bulk/create" in routes
        assert "POST" in routes["/data/bulk/create"].methods
    
    def test_bulk_update_endpoint_exists(self):
        """Test bulk update endpoint is registered."""
        from app.api.v1.data import router
        
        routes = {route.path: route for route in router.routes}
        assert "/data/bulk/update" in routes
        assert "POST" in routes["/data/bulk/update"].methods
    
    def test_bulk_delete_endpoint_exists(self):
        """Test bulk delete endpoint is registered."""
        from app.api.v1.data import router
        
        routes = {route.path: route for route in router.routes}
        assert "/data/bulk/delete" in routes
        assert "POST" in routes["/data/bulk/delete"].methods
    
    def test_aggregate_endpoint_exists(self):
        """Test aggregate query endpoint is registered."""
        from app.api.v1.data import router
        
        routes = {route.path: route for route in router.routes}
        assert "/data/aggregate" in routes
        assert "POST" in routes["/data/aggregate"].methods
    
    def test_export_endpoint_exists(self):
        """Test export endpoint is registered."""
        from app.api.v1.data import router
        
        routes = {route.path: route for route in router.routes}
        assert "/data/export" in routes
        assert "POST" in routes["/data/export"].methods
    
    def test_import_endpoint_exists(self):
        """Test import endpoint is registered."""
        from app.api.v1.data import router
        
        routes = {route.path: route for route in router.routes}
        assert "/data/import" in routes
        assert "POST" in routes["/data/import"].methods


# ============================================================================
# SecureQueryBuilder Aggregation Tests
# ============================================================================

class TestSecureQueryBuilderAggregation:
    """Test SecureQueryBuilder aggregation query building."""
    
    def test_build_aggregate_exists(self):
        """Test build_aggregate method exists."""
        from app.services.permissions.secure_query_builder import SecureQueryBuilder
        assert hasattr(SecureQueryBuilder, 'build_aggregate')
    
    def test_build_aggregate_simple_count(self):
        """Test building simple COUNT(*) aggregation."""
        from app.services.permissions.secure_query_builder import SecureQueryBuilder
        from app.services.permissions.permission_checker import Scope, FieldAccess
        from uuid import uuid4
        
        builder = SecureQueryBuilder(
            schema_name="tenant_test",
            table_name="test_employee",
            user_id=uuid4(),
            scope=Scope.ALL,
            field_access={"department": FieldAccess.READ}
        )
        
        sql, params = builder.build_aggregate(
            aggregations=[{"field": "*", "function": "count", "alias": "total"}],
            group_by=None
        )
        
        assert "COUNT(*)" in sql
        assert "tenant_test.test_employee" in sql
    
    def test_build_aggregate_with_group_by(self):
        """Test building aggregation with GROUP BY."""
        from app.services.permissions.secure_query_builder import SecureQueryBuilder
        from app.services.permissions.permission_checker import Scope, FieldAccess
        from uuid import uuid4
        
        builder = SecureQueryBuilder(
            schema_name="tenant_test",
            table_name="test_employee",
            user_id=uuid4(),
            scope=Scope.ALL,
            field_access={
                "department": FieldAccess.READ,
                "salary": FieldAccess.READ
            }
        )
        
        sql, params = builder.build_aggregate(
            aggregations=[
                {"field": "*", "function": "count", "alias": "count"},
                {"field": "salary", "function": "avg", "alias": "avg_salary"}
            ],
            group_by=["department"]
        )
        
        assert "GROUP BY" in sql
        assert "department" in sql
        assert "COUNT(*)" in sql
        assert "AVG(salary)" in sql or "avg(salary)" in sql
    
    def test_build_aggregate_with_having(self):
        """Test building aggregation with HAVING clause."""
        from app.services.permissions.secure_query_builder import SecureQueryBuilder, QueryFilter
        from app.services.permissions.permission_checker import Scope, FieldAccess
        from uuid import uuid4
        
        builder = SecureQueryBuilder(
            schema_name="tenant_test",
            table_name="test_employee",
            user_id=uuid4(),
            scope=Scope.ALL,
            field_access={"department": FieldAccess.READ}
        )
        
        sql, params = builder.build_aggregate(
            aggregations=[{"field": "*", "function": "count", "alias": "employee_count"}],
            group_by=["department"],
            having=[QueryFilter("employee_count", "gt", 5)]
        )
        
        assert "HAVING" in sql
        assert "employee_count" in sql


# ============================================================================
# Permission Checker Tests for Bulk Operations
# ============================================================================

class TestPermissionCheckerBulkOperations:
    """Test PermissionChecker bulk operation methods."""
    
    def test_can_bulk_operation_export(self):
        """Test can_bulk_operation for export."""
        from app.services.permissions.permission_checker import PermissionChecker
        
        # Using bulk:* wildcard gives access to all bulk operations
        permissions = ["bulk:*"]
        assert PermissionChecker.can_bulk_operation(permissions, "export") is True
    
    def test_can_bulk_operation_import(self):
        """Test can_bulk_operation for import."""
        from app.services.permissions.permission_checker import PermissionChecker
        
        # Using bulk:* wildcard gives access to all bulk operations
        permissions = ["bulk:*"]
        assert PermissionChecker.can_bulk_operation(permissions, "import") is True
    
    def test_can_bulk_operation_denied(self):
        """Test can_bulk_operation denies when no permission."""
        from app.services.permissions.permission_checker import PermissionChecker
        
        permissions = ["data:read:*"]
        assert PermissionChecker.can_bulk_operation(permissions, "export") is False
    
    def test_get_export_formats_all(self):
        """Test get_export_formats with wildcard."""
        from app.services.permissions.permission_checker import PermissionChecker
        
        permissions = ["bulk:export:format:*"]
        formats = PermissionChecker.get_export_formats(permissions)
        # Wildcard expands to all supported formats
        assert "csv" in formats
        assert "json" in formats
        assert "excel" in formats
        assert "parquet" in formats
    
    def test_get_export_formats_specific(self):
        """Test get_export_formats with specific formats."""
        from app.services.permissions.permission_checker import PermissionChecker
        
        permissions = ["bulk:export:format:csv", "bulk:export:format:json"]
        formats = PermissionChecker.get_export_formats(permissions)
        assert "csv" in formats
        assert "json" in formats
        assert "excel" not in formats


# ============================================================================
# Export/Import Helper Function Tests
# ============================================================================

class TestExportImportHelpers:
    """Test export/import helper functions."""
    
    def test_export_to_csv_helper_exists(self):
        """Test CSV export helper function exists."""
        from app.api.v1 import data
        assert hasattr(data, '_export_to_csv')
    
    def test_export_to_json_helper_exists(self):
        """Test JSON export helper function exists."""
        from app.api.v1 import data
        assert hasattr(data, '_export_to_json')
    
    def test_export_to_excel_helper_exists(self):
        """Test Excel export helper function exists."""
        from app.api.v1 import data
        assert hasattr(data, '_export_to_excel')
    
    def test_parse_csv_helper_exists(self):
        """Test CSV parse helper function exists."""
        from app.api.v1 import data
        assert hasattr(data, '_parse_csv')
    
    def test_parse_json_helper_exists(self):
        """Test JSON parse helper function exists."""
        from app.api.v1 import data
        assert hasattr(data, '_parse_json')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
