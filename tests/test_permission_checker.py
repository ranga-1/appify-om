"""Unit tests for PermissionChecker class."""

import pytest
from app.services.permissions.permission_checker import (
    PermissionChecker,
    FieldAccess,
    Scope
)


class TestPermissionChecker:
    """Test suite for PermissionChecker."""
    
    # ========================================================================
    # has_permission() Tests
    # ========================================================================
    
    def test_has_permission_direct_match(self):
        """Test direct permission match."""
        permissions = ["data:read:scope:all", "data:create"]
        assert PermissionChecker.has_permission(permissions, "data:read:scope:all")
        assert PermissionChecker.has_permission(permissions, "data:create")
    
    def test_has_permission_wildcard_resource(self):
        """Test wildcard at resource level."""
        permissions = ["data:*"]
        assert PermissionChecker.has_permission(permissions, "data:read")
        assert PermissionChecker.has_permission(permissions, "data:create")
        assert PermissionChecker.has_permission(permissions, "data:update")
        assert PermissionChecker.has_permission(permissions, "data:delete")
    
    def test_has_permission_wildcard_action(self):
        """Test wildcard at action level."""
        permissions = ["data:read:*"]
        assert PermissionChecker.has_permission(permissions, "data:read:scope:all")
        assert PermissionChecker.has_permission(permissions, "data:read:scope:team")
        assert not PermissionChecker.has_permission(permissions, "data:create")
    
    def test_has_permission_admin_wildcard(self):
        """Test admin wildcard grants everything."""
        permissions = ["admin:*"]
        assert PermissionChecker.has_permission(permissions, "admin:delete:users")
        assert PermissionChecker.has_permission(permissions, "admin:manage:roles")
    
    def test_has_permission_no_match(self):
        """Test permission denied."""
        permissions = ["data:read:scope:self"]
        assert not PermissionChecker.has_permission(permissions, "data:update")
        assert not PermissionChecker.has_permission(permissions, "data:read:scope:all")
    
    def test_has_permission_empty_permissions(self):
        """Test with no permissions."""
        permissions = []
        assert not PermissionChecker.has_permission(permissions, "data:read")
    
    # ========================================================================
    # get_data_scope() Tests
    # ========================================================================
    
    def test_get_data_scope_all(self):
        """Test scope extraction for 'all' scope."""
        permissions = ["data:read:scope:all"]
        scope = PermissionChecker.get_data_scope(permissions, "read")
        assert scope == Scope.ALL
    
    def test_get_data_scope_team(self):
        """Test scope extraction for 'team' scope."""
        permissions = ["data:read:scope:team"]
        scope = PermissionChecker.get_data_scope(permissions, "read")
        assert scope == Scope.TEAM
    
    def test_get_data_scope_self(self):
        """Test scope extraction for 'self' scope."""
        permissions = ["data:read:scope:self"]
        scope = PermissionChecker.get_data_scope(permissions, "read")
        assert scope == Scope.SELF
    
    def test_get_data_scope_department(self):
        """Test scope extraction for 'department' scope."""
        permissions = ["data:read:scope:department"]
        scope = PermissionChecker.get_data_scope(permissions, "read")
        assert scope == Scope.DEPARTMENT
    
    def test_get_data_scope_wildcard_grants_all(self):
        """Test wildcard grants all scope."""
        permissions = ["data:*"]
        scope = PermissionChecker.get_data_scope(permissions, "update")
        assert scope == Scope.ALL
    
    def test_get_data_scope_admin_grants_all(self):
        """Test admin wildcard grants all scope."""
        permissions = ["admin:*"]
        scope = PermissionChecker.get_data_scope(permissions, "read")
        assert scope == Scope.ALL
    
    def test_get_data_scope_most_permissive(self):
        """Test that most permissive scope wins."""
        permissions = ["data:read:scope:self", "data:read:scope:all"]
        scope = PermissionChecker.get_data_scope(permissions, "read")
        assert scope == Scope.ALL
    
    def test_get_data_scope_none_by_default(self):
        """Test default scope is NONE."""
        permissions = ["data:create"]
        scope = PermissionChecker.get_data_scope(permissions, "read")
        assert scope == Scope.NONE
    
    # ========================================================================
    # filter_fields() Tests
    # ========================================================================
    
    def test_filter_fields_read_wildcard(self):
        """Test field:read:* grants read access to all fields."""
        permissions = ["field:read:*"]
        all_fields = ["name", "email", "salary"]
        field_access = PermissionChecker.filter_fields(permissions, all_fields)
        
        assert field_access["name"] == FieldAccess.READ
        assert field_access["email"] == FieldAccess.READ
        assert field_access["salary"] == FieldAccess.READ
    
    def test_filter_fields_write_wildcard(self):
        """Test field:write:* grants write access to all fields."""
        permissions = ["field:write:*"]
        all_fields = ["name", "email"]
        field_access = PermissionChecker.filter_fields(permissions, all_fields)
        
        assert field_access["name"] == FieldAccess.WRITE
        assert field_access["email"] == FieldAccess.WRITE
    
    def test_filter_fields_admin_wildcard(self):
        """Test admin:* grants write access to all fields."""
        permissions = ["admin:*"]
        all_fields = ["name", "email", "salary"]
        field_access = PermissionChecker.filter_fields(permissions, all_fields)
        
        assert field_access["name"] == FieldAccess.WRITE
        assert field_access["email"] == FieldAccess.WRITE
        assert field_access["salary"] == FieldAccess.WRITE
    
    def test_filter_fields_specific_mask(self):
        """Test specific field masking."""
        permissions = ["field:read:*", "field:mask:salary"]
        all_fields = ["name", "salary"]
        field_access = PermissionChecker.filter_fields(permissions, all_fields)
        
        assert field_access["name"] == FieldAccess.READ
        assert field_access["salary"] == FieldAccess.MASK
    
    def test_filter_fields_specific_hide(self):
        """Test specific field hiding."""
        permissions = ["field:read:*", "field:hide:ssn"]
        all_fields = ["name", "ssn"]
        field_access = PermissionChecker.filter_fields(permissions, all_fields)
        
        assert field_access["name"] == FieldAccess.READ
        assert field_access["ssn"] == FieldAccess.HIDE
    
    def test_filter_fields_mixed_permissions(self):
        """Test mixed field permissions."""
        permissions = ["field:read:*", "field:write:name", "field:mask:salary"]
        all_fields = ["name", "email", "salary"]
        field_access = PermissionChecker.filter_fields(permissions, all_fields)
        
        assert field_access["name"] == FieldAccess.WRITE
        assert field_access["email"] == FieldAccess.READ
        assert field_access["salary"] == FieldAccess.MASK
    
    def test_filter_fields_with_object_prefix(self):
        """Test field permissions with object prefix."""
        permissions = ["field:read:*", "field:mask:abc12_salary"]
        all_fields = ["abc12_name", "abc12_salary"]
        field_access = PermissionChecker.filter_fields(permissions, all_fields, "abc12")
        
        assert field_access["abc12_name"] == FieldAccess.READ
        assert field_access["abc12_salary"] == FieldAccess.MASK
    
    def test_filter_fields_fail_closed(self):
        """Test that fields are hidden by default (fail-closed)."""
        permissions = []
        all_fields = ["name", "email"]
        field_access = PermissionChecker.filter_fields(permissions, all_fields)
        
        assert field_access["name"] == FieldAccess.HIDE
        assert field_access["email"] == FieldAccess.HIDE
    
    # ========================================================================
    # can_bulk_operation() Tests
    # ========================================================================
    
    def test_can_bulk_operation_specific(self):
        """Test specific bulk operation permission."""
        permissions = ["bulk:export"]
        assert PermissionChecker.can_bulk_operation(permissions, "export")
    
    def test_can_bulk_operation_wildcard(self):
        """Test bulk wildcard permission."""
        permissions = ["bulk:*"]
        assert PermissionChecker.can_bulk_operation(permissions, "export")
        assert PermissionChecker.can_bulk_operation(permissions, "import")
        assert PermissionChecker.can_bulk_operation(permissions, "delete")
    
    def test_can_bulk_operation_admin(self):
        """Test admin wildcard grants bulk operations."""
        permissions = ["admin:*"]
        assert PermissionChecker.can_bulk_operation(permissions, "export")
    
    def test_can_bulk_operation_denied(self):
        """Test bulk operation denied."""
        permissions = ["data:read:scope:all"]
        assert not PermissionChecker.can_bulk_operation(permissions, "export")
    
    # ========================================================================
    # can_use_query_type() Tests
    # ========================================================================
    
    def test_can_use_query_type_basic(self):
        """Test basic query permission."""
        permissions = ["query:basic"]
        assert PermissionChecker.can_use_query_type(permissions, "basic")
        assert not PermissionChecker.can_use_query_type(permissions, "advanced")
    
    def test_can_use_query_type_advanced(self):
        """Test advanced query permission."""
        permissions = ["query:advanced"]
        assert PermissionChecker.can_use_query_type(permissions, "advanced")
        assert not PermissionChecker.can_use_query_type(permissions, "aggregation")
    
    def test_can_use_query_type_wildcard(self):
        """Test query wildcard permission."""
        permissions = ["query:*"]
        assert PermissionChecker.can_use_query_type(permissions, "basic")
        assert PermissionChecker.can_use_query_type(permissions, "advanced")
        assert PermissionChecker.can_use_query_type(permissions, "aggregation")
    
    def test_can_use_query_type_admin(self):
        """Test admin grants all query types."""
        permissions = ["admin:*"]
        assert PermissionChecker.can_use_query_type(permissions, "aggregation")
    
    # ========================================================================
    # get_export_formats() Tests
    # ========================================================================
    
    def test_get_export_formats_specific(self):
        """Test specific export format."""
        permissions = ["bulk:export:format:csv"]
        formats = PermissionChecker.get_export_formats(permissions)
        assert formats == {"csv"}
    
    def test_get_export_formats_multiple(self):
        """Test multiple export formats."""
        permissions = ["bulk:export:format:csv", "bulk:export:format:json"]
        formats = PermissionChecker.get_export_formats(permissions)
        assert formats == {"csv", "json"}
    
    def test_get_export_formats_wildcard(self):
        """Test export format wildcard."""
        permissions = ["bulk:export:format:*"]
        formats = PermissionChecker.get_export_formats(permissions)
        assert formats == {"csv", "json", "excel", "parquet"}
    
    def test_get_export_formats_admin(self):
        """Test admin grants all formats."""
        permissions = ["admin:*"]
        formats = PermissionChecker.get_export_formats(permissions)
        assert formats == {"csv", "json", "excel", "parquet"}
    
    def test_get_export_formats_none(self):
        """Test no export formats."""
        permissions = ["data:read:scope:all"]
        formats = PermissionChecker.get_export_formats(permissions)
        assert formats == set()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
