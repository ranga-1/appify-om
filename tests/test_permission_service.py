"""Unit tests for PermissionService class."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from uuid import UUID, uuid4
import json
from app.services.permissions.permission_service import (
    PermissionService,
    PermissionSet
)
from app.services.permissions.permission_checker import FieldAccess


class TestPermissionSet:
    """Test suite for PermissionSet dataclass."""
    
    def test_permission_set_to_dict(self):
        """Test PermissionSet serialization to dict."""
        user_id = uuid4()
        object_id = uuid4()
        field_permissions = {"name": FieldAccess.WRITE, "email": FieldAccess.READ}
        
        pset = PermissionSet(
            user_id=user_id,
            object_id=object_id,
            permissions=["data:read:*", "data:write:employee"],
            field_permissions=field_permissions,
            row_filter="created_by = 'user123'"
        )
        
        data = pset.to_dict()
        
        assert data["user_id"] == str(user_id)
        assert data["object_id"] == str(object_id)
        assert data["permissions"] == ["data:read:*", "data:write:employee"]
        assert data["field_permissions"] == {"name": "write", "email": "read"}
        assert data["row_filter"] == "created_by = 'user123'"
    
    def test_permission_set_from_dict(self):
        """Test PermissionSet deserialization from dict."""
        user_id = uuid4()
        object_id = uuid4()
        
        data = {
            "user_id": str(user_id),
            "object_id": str(object_id),
            "permissions": ["data:read:*"],
            "field_permissions": {"name": "read"},
            "row_filter": "status = 'active'"
        }
        
        pset = PermissionSet.from_dict(data)
        
        assert pset.user_id == user_id
        assert pset.object_id == object_id
        assert pset.permissions == ["data:read:*"]
        assert pset.field_permissions == {"name": FieldAccess.READ}
        assert pset.row_filter == "status = 'active'"


class TestPermissionService:
    """Test suite for PermissionService."""
    
    @pytest.fixture
    def user_id(self):
        """Test user ID."""
        return uuid4()
    
    @pytest.fixture
    def object_id(self):
        """Test object ID."""
        return uuid4()
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis_mock = MagicMock()
        redis_mock.get.return_value = None  # Cache miss by default
        redis_mock.ping.return_value = True
        return redis_mock
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db_mock = MagicMock()
        return db_mock
    
    @pytest.fixture
    def service(self, mock_redis, mock_db):
        """PermissionService instance with mocked dependencies."""
        with patch('redis.Redis', return_value=mock_redis):
            service = PermissionService(db_session=mock_db)
            return service
    
    # ========================================================================
    # get_user_permissions() Tests - Cache Hit
    # ========================================================================
    
    def test_get_user_permissions_cache_hit(self, service, user_id, object_id, mock_redis):
        """Test cache hit returns cached permissions."""
        # Create permission set to cache
        pset = PermissionSet(
            user_id=user_id,
            object_id=object_id,
            permissions=["data:read:*", "data:write:employee"],
            field_permissions={"name": FieldAccess.WRITE, "email": FieldAccess.READ},
            row_filter=None
        )
        
        mock_redis.get.return_value = json.dumps(pset.to_dict())
        
        result = service.get_user_permissions(
            user_id=user_id,
            object_id=object_id,
            all_fields=["name", "email"]
        )
        
        assert isinstance(result, PermissionSet)
        assert result.user_id == user_id
        assert result.object_id == object_id
        assert "data:read:*" in result.permissions
        assert "data:write:employee" in result.permissions
        
        # Verify cache was checked
        cache_key = f"perms:{user_id}:{object_id}"
        mock_redis.get.assert_called_once_with(cache_key)
    
    # ========================================================================
    # get_user_permissions() Tests - Cache Miss, DB Query
    # ========================================================================
    
    def test_get_user_permissions_cache_miss_single_role(self, service, user_id, object_id, mock_redis, mock_db):
        """Test cache miss queries database and caches result."""
        mock_redis.get.return_value = None  # Cache miss
        
        # Mock database query results
        db_row = MagicMock()
        db_row.permissions = ["data:read:*", "data:write:employee"]
        db_row.row_filter = None
        db_row.field_permissions = None
        
        result_mock = MagicMock()
        result_mock.__iter__ = Mock(return_value=iter([db_row]))
        
        mock_db.execute.return_value = result_mock
        
        result = service.get_user_permissions(
            user_id=user_id,
            object_id=object_id,
            all_fields=["name", "email"]
        )
        
        assert isinstance(result, PermissionSet)
        assert result.user_id == user_id
        assert result.object_id == object_id
        assert "data:read:*" in result.permissions
        assert "data:write:employee" in result.permissions
        
        # Verify cache was set
        cache_key = f"perms:{user_id}:{object_id}"
        assert mock_redis.setex.called
        assert mock_redis.setex.call_args[0][0] == cache_key
    
    def test_get_user_permissions_multiple_roles_merge(self, service, user_id, object_id, mock_redis, mock_db):
        """Test merging permissions from multiple roles."""
        mock_redis.get.return_value = None  # Cache miss
        
        # Two roles with different permissions
        row1 = MagicMock()
        row1.permissions = ["data:read:*", "data:write:employee"]
        row1.row_filter = None
        row1.field_permissions = None
        
        row2 = MagicMock()
        row2.permissions = ["data:read:*", "data:write:customer"]  # Duplicate data:read:*
        row2.row_filter = None
        row2.field_permissions = None
        
        result_mock = MagicMock()
        result_mock.__iter__ = Mock(return_value=iter([row1, row2]))
        
        mock_db.execute.return_value = result_mock
        
        result = service.get_user_permissions(
            user_id=user_id,
            object_id=object_id,
            all_fields=["name"]
        )
        
        # Verify permissions are merged and deduplicated
        assert "data:read:*" in result.permissions
        assert "data:write:employee" in result.permissions
        assert "data:write:customer" in result.permissions
        # Should not have duplicates
        assert result.permissions.count("data:read:*") == 1
    
    def test_get_user_permissions_no_roles(self, service, user_id, object_id, mock_redis, mock_db):
        """Test user with no roles returns empty permission set."""
        mock_redis.get.return_value = None  # Cache miss
        
        result_mock = MagicMock()
        result_mock.__iter__ = Mock(return_value=iter([]))  # Empty result
        
        mock_db.execute.return_value = result_mock
        
        result = service.get_user_permissions(
            user_id=user_id,
            object_id=object_id,
            all_fields=[]
        )
        
        assert isinstance(result, PermissionSet)
        assert result.permissions == []
    
    # ========================================================================
    # invalidate_user_permissions() Tests
    # ========================================================================
    
    def test_invalidate_user_permissions(self, service, user_id, mock_redis):
        """Test cache invalidation for user."""
        # Mock keys() to return some cached permission keys
        mock_redis.keys.return_value = [
            f"perms:{user_id}:obj1",
            f"perms:{user_id}:obj2"
        ]
        
        service.invalidate_user_permissions(user_id)
        
        # Verify pattern search
        pattern = f"perms:{user_id}:*"
        mock_redis.keys.assert_called_once_with(pattern)
        
        # Verify delete was called with the keys
        assert mock_redis.delete.called
    
    # ========================================================================
    # invalidate_object_permissions() Tests
    # ========================================================================
    
    def test_invalidate_object_permissions(self, service, object_id, mock_redis):
        """Test cache invalidation for entire object (all users)."""
        # Mock keys() to return some cached permission keys
        mock_redis.keys.return_value = [
            f"perms:user1:{object_id}",
            f"perms:user2:{object_id}",
            f"perms:user3:{object_id}"
        ]
        
        service.invalidate_object_permissions(object_id)
        
        # Verify pattern search
        pattern = f"perms:*:{object_id}"
        mock_redis.keys.assert_called_once_with(pattern)
        
        # Verify delete was called
        assert mock_redis.delete.called
    
    # ========================================================================
    # Edge Cases
    # ========================================================================
    
    def test_redis_connection_error_falls_back_to_db(self, user_id, object_id, mock_db):
        """Test that Redis errors don't break the service."""
        # Create service with Redis that fails to connect
        mock_redis_fail = MagicMock()
        mock_redis_fail.ping.side_effect = Exception("Connection failed")
        
        with patch('redis.Redis', return_value=mock_redis_fail):
            service = PermissionService(db_session=mock_db)
            
            # Mock DB result
            result_mock = MagicMock()
            result_mock.__iter__ = Mock(return_value=iter([]))
            mock_db.execute.return_value = result_mock
            
            # Should still work by querying DB
            result = service.get_user_permissions(
                user_id=user_id,
                object_id=object_id,
                all_fields=[]
            )
            
            assert isinstance(result, PermissionSet)
            # Redis should be None after failed connection
            assert service._redis_client is None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
