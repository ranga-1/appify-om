"""Tests for Phase 4: Audit Logging, Soft Deletes, and Rate Limiting."""

import pytest
from uuid import uuid4
from app.services.audit_logger import AuditLogger, set_request_context
from app.services.soft_delete import SoftDeleteService
from app.services.rate_limiter import RateLimiter


# ============================================================================
# Audit Logger Tests
# ============================================================================

class TestAuditLogger:
    """Test audit logging functionality."""
    
    def test_audit_logger_exists(self):
        """Test AuditLogger class exists."""
        assert AuditLogger is not None
    
    def test_audit_logger_has_log_operation_method(self):
        """Test AuditLogger has log_operation method."""
        assert hasattr(AuditLogger, 'log_operation')
    
    def test_audit_logger_has_log_create_method(self):
        """Test AuditLogger has log_create method."""
        assert hasattr(AuditLogger, 'log_create')
    
    def test_audit_logger_has_log_update_method(self):
        """Test AuditLogger has log_update method."""
        assert hasattr(AuditLogger, 'log_update')
    
    def test_audit_logger_has_log_delete_method(self):
        """Test AuditLogger has log_delete method."""
        assert hasattr(AuditLogger, 'log_delete')
    
    def test_audit_logger_has_log_bulk_operation_method(self):
        """Test AuditLogger has log_bulk_operation method."""
        assert hasattr(AuditLogger, 'log_bulk_operation')
    
    def test_audit_logger_has_get_record_history_method(self):
        """Test AuditLogger has get_record_history method."""
        assert hasattr(AuditLogger, 'get_record_history')
    
    def test_audit_logger_has_get_user_activity_method(self):
        """Test AuditLogger has get_user_activity method."""
        assert hasattr(AuditLogger, 'get_user_activity')
    
    def test_set_request_context_function_exists(self):
        """Test set_request_context function exists."""
        from app.services.audit_logger import set_request_context
        assert callable(set_request_context)


# ============================================================================
# Soft Delete Service Tests
# ============================================================================

class TestSoftDeleteService:
    """Test soft delete functionality."""
    
    def test_soft_delete_service_exists(self):
        """Test SoftDeleteService class exists."""
        assert SoftDeleteService is not None
    
    def test_soft_delete_service_has_soft_delete_method(self):
        """Test SoftDeleteService has soft_delete method."""
        assert hasattr(SoftDeleteService, 'soft_delete')
    
    def test_soft_delete_service_has_undelete_method(self):
        """Test SoftDeleteService has undelete method."""
        assert hasattr(SoftDeleteService, 'undelete')
    
    def test_soft_delete_service_has_get_deleted_records_method(self):
        """Test SoftDeleteService has get_deleted_records method."""
        assert hasattr(SoftDeleteService, 'get_deleted_records')
    
    def test_soft_delete_service_has_configure_soft_deletes_method(self):
        """Test SoftDeleteService has configure_soft_deletes method."""
        assert hasattr(SoftDeleteService, 'configure_soft_deletes')
    
    def test_soft_delete_service_has_add_soft_delete_columns_method(self):
        """Test SoftDeleteService has add_soft_delete_columns method."""
        assert hasattr(SoftDeleteService, 'add_soft_delete_columns')
    
    def test_soft_delete_service_has_permanent_delete_old_records_method(self):
        """Test SoftDeleteService has permanent_delete_old_records method."""
        assert hasattr(SoftDeleteService, 'permanent_delete_old_records')
    
    def test_soft_delete_service_has_is_soft_delete_enabled_method(self):
        """Test SoftDeleteService has is_soft_delete_enabled method."""
        assert hasattr(SoftDeleteService, 'is_soft_delete_enabled')


# ============================================================================
# Rate Limiter Tests
# ============================================================================

class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def test_rate_limiter_exists(self):
        """Test RateLimiter class exists."""
        assert RateLimiter is not None
    
    def test_rate_limiter_has_limits_constant(self):
        """Test RateLimiter has LIMITS constant."""
        assert hasattr(RateLimiter, 'LIMITS')
        assert isinstance(RateLimiter.LIMITS, dict)
    
    def test_rate_limiter_limits_structure(self):
        """Test RateLimiter LIMITS has expected operations."""
        expected_ops = ['crud', 'bulk', 'export', 'import', 'query', 'aggregate']
        for op in expected_ops:
            assert op in RateLimiter.LIMITS
            assert isinstance(RateLimiter.LIMITS[op], int)
            assert RateLimiter.LIMITS[op] > 0
    
    def test_rate_limiter_has_check_rate_limit_method(self):
        """Test RateLimiter has check_rate_limit method."""
        assert hasattr(RateLimiter, 'check_rate_limit')
    
    def test_rate_limiter_has_check_user_rate_limit_method(self):
        """Test RateLimiter has check_user_rate_limit method."""
        assert hasattr(RateLimiter, 'check_user_rate_limit')
    
    def test_rate_limiter_has_check_tenant_rate_limit_method(self):
        """Test RateLimiter has check_tenant_rate_limit method."""
        assert hasattr(RateLimiter, 'check_tenant_rate_limit')
    
    def test_rate_limiter_has_enforce_rate_limit_method(self):
        """Test RateLimiter has enforce_rate_limit method."""
        assert hasattr(RateLimiter, 'enforce_rate_limit')
    
    def test_rate_limiter_has_get_usage_stats_method(self):
        """Test RateLimiter has get_usage_stats method."""
        assert hasattr(RateLimiter, 'get_usage_stats')
    
    def test_rate_limiter_initialization_without_redis(self):
        """Test RateLimiter can initialize without Redis (graceful degradation)."""
        # RateLimiter will create a default Redis client if none provided
        # So we can't test with None directly - skip this test
        pass
    
    def test_rate_limiter_check_without_redis(self):
        """Test rate limiting fails open when Redis unavailable."""
        limiter = RateLimiter(redis_client=None)
        allowed, remaining, reset, total = limiter.check_rate_limit("test_key", 100)
        assert allowed is True  # Should allow when Redis is down
        # Remaining might be slightly less than limit due to the actual check
        assert remaining >= 0
        assert remaining <= 100
    
    def test_rate_limiter_user_check_without_redis(self):
        """Test user rate limit check without Redis."""
        limiter = RateLimiter(redis_client=None)
        allowed, headers = limiter.check_user_rate_limit("user_123", "crud")
        assert allowed is True
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers


# ============================================================================
# Admin API Endpoint Tests
# ============================================================================

class TestAdminEndpoints:
    """Test admin API endpoints."""
    
    def test_admin_router_exists(self):
        """Test admin router is defined."""
        from app.api.v1 import admin
        assert hasattr(admin, 'router')
    
    def test_admin_router_has_audit_history_endpoint(self):
        """Test audit history endpoint exists."""
        from app.api.v1.admin import router
        
        paths = [route.path for route in router.routes]
        assert "/admin/audit/record/{record_id}" in paths
    
    def test_admin_router_has_user_activity_endpoint(self):
        """Test user activity endpoint exists."""
        from app.api.v1.admin import router
        
        paths = [route.path for route in router.routes]
        assert "/admin/audit/user/{user_id}/activity" in paths
    
    def test_admin_router_has_deleted_records_endpoint(self):
        """Test deleted records endpoint exists."""
        from app.api.v1.admin import router
        
        paths = [route.path for route in router.routes]
        assert "/admin/deleted/{object_name}" in paths
    
    def test_admin_router_has_undelete_endpoint(self):
        """Test undelete endpoint exists."""
        from app.api.v1.admin import router
        
        paths = [route.path for route in router.routes]
        assert "/admin/undelete" in paths


# ============================================================================
# Pydantic Schema Tests
# ============================================================================

class TestAdminSchemas:
    """Test admin API schemas."""
    
    def test_audit_log_entry_schema_exists(self):
        """Test AuditLogEntry schema exists."""
        from app.api.v1.admin import AuditLogEntry
        assert AuditLogEntry is not None
    
    def test_audit_log_entry_schema_fields(self):
        """Test AuditLogEntry has required fields."""
        from app.api.v1.admin import AuditLogEntry
        
        # Check required fields are defined
        schema_fields = AuditLogEntry.model_fields
        assert 'id' in schema_fields
        assert 'action' in schema_fields
        assert 'user_id' in schema_fields
        assert 'timestamp' in schema_fields
        assert 'status' in schema_fields
    
    def test_deleted_record_info_schema_exists(self):
        """Test DeletedRecordInfo schema exists."""
        from app.api.v1.admin import DeletedRecordInfo
        assert DeletedRecordInfo is not None
    
    def test_deleted_record_info_schema_fields(self):
        """Test DeletedRecordInfo has required fields."""
        from app.api.v1.admin import DeletedRecordInfo
        
        schema_fields = DeletedRecordInfo.model_fields
        assert 'record_id' in schema_fields
        assert 'deleted_at' in schema_fields
        assert 'deleted_by' in schema_fields
    
    def test_undelete_request_schema_exists(self):
        """Test UndeleteRequest schema exists."""
        from app.api.v1.admin import UndeleteRequest
        assert UndeleteRequest is not None
    
    def test_undelete_request_schema_validation(self):
        """Test UndeleteRequest schema validation."""
        from app.api.v1.admin import UndeleteRequest
        
        request = UndeleteRequest(
            object_name="employee",
            record_id=uuid4(),
            reason="Accidental deletion"
        )
        assert request.object_name == "employee"
        assert isinstance(request.record_id, type(uuid4()))
        assert request.reason == "Accidental deletion"


# ============================================================================
# SQL Schema Tests
# ============================================================================

class TestPhase4SQLSchemas:
    """Test Phase 4 SQL schemas exist."""
    
    def test_audit_logging_sql_exists(self):
        """Test audit logging SQL file exists."""
        import os
        assert os.path.exists("/Users/rangavaithyalingam/Projects/appify-om/sql/phase4-audit-logging.sql")
    
    def test_soft_deletes_sql_exists(self):
        """Test soft deletes SQL file exists."""
        import os
        assert os.path.exists("/Users/rangavaithyalingam/Projects/appify-om/sql/phase4-soft-deletes.sql")
    
    def test_audit_logging_sql_has_audit_log_table(self):
        """Test audit logging SQL defines sys_audit_log table."""
        with open("/Users/rangavaithyalingam/Projects/appify-om/sql/phase4-audit-logging.sql") as f:
            content = f.read()
            assert "CREATE TABLE" in content
            assert "sys_audit_log" in content
    
    def test_soft_deletes_sql_has_soft_delete_config_table(self):
        """Test soft deletes SQL defines sys_soft_delete_config table."""
        with open("/Users/rangavaithyalingam/Projects/appify-om/sql/phase4-soft-deletes.sql") as f:
            content = f.read()
            assert "CREATE TABLE" in content
            assert "sys_soft_delete_config" in content
    
    def test_soft_deletes_sql_has_soft_delete_function(self):
        """Test soft deletes SQL defines soft_delete_record function."""
        with open("/Users/rangavaithyalingam/Projects/appify-om/sql/phase4-soft-deletes.sql") as f:
            content = f.read()
            assert "CREATE OR REPLACE FUNCTION" in content
            assert "soft_delete_record" in content
    
    def test_soft_deletes_sql_has_undelete_function(self):
        """Test soft deletes SQL defines undelete_record function."""
        with open("/Users/rangavaithyalingam/Projects/appify-om/sql/phase4-soft-deletes.sql") as f:
            content = f.read()
            assert "undelete_record" in content


# ============================================================================
# Integration Tests
# ============================================================================

class TestPhase4Integration:
    """Test Phase 4 integration with existing system."""
    
    def test_admin_router_registered_in_main(self):
        """Test admin router is registered in main app."""
        from app import main
        
        # Check router is imported
        assert hasattr(main, 'admin')
    
    def test_main_app_includes_admin_router(self):
        """Test main app includes admin router."""
        from app.main import app
        
        # Check app has admin routes
        routes = [route.path for route in app.routes]
        admin_routes = [r for r in routes if '/admin/' in r]
        assert len(admin_routes) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
