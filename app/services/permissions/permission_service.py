"""Permission resolution service with Redis caching."""

import json
import logging
from typing import List, Dict, Optional, Set
from uuid import UUID
import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from .permission_checker import PermissionChecker, Scope, FieldAccess

logger = logging.getLogger(__name__)


class PermissionSet:
    """Represents a user's complete permission set for an object."""
    
    def __init__(
        self,
        user_id: UUID,
        object_id: UUID,
        permissions: List[str],
        field_permissions: Dict[str, FieldAccess],
        row_filter: Optional[str] = None
    ):
        """
        Initialize permission set.
        
        Args:
            user_id: User UUID
            object_id: Object UUID
            permissions: List of permission strings
            field_permissions: Dictionary of field name to access level
            row_filter: Optional SQL WHERE clause for row-level security
        """
        self.user_id = user_id
        self.object_id = object_id
        self.permissions = permissions
        self.field_permissions = field_permissions
        self.row_filter = row_filter
    
    def to_dict(self) -> dict:
        """Convert to dictionary for caching."""
        return {
            "user_id": str(self.user_id),
            "object_id": str(self.object_id),
            "permissions": self.permissions,
            "field_permissions": {k: v.value for k, v in self.field_permissions.items()},
            "row_filter": self.row_filter
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PermissionSet":
        """Create from cached dictionary."""
        return cls(
            user_id=UUID(data["user_id"]),
            object_id=UUID(data["object_id"]),
            permissions=data["permissions"],
            field_permissions={k: FieldAccess(v) for k, v in data["field_permissions"].items()},
            row_filter=data.get("row_filter")
        )


class PermissionService:
    """
    Service for resolving and caching user permissions.
    
    This service:
    1. Queries database for user roles and permissions
    2. Merges permissions from multiple roles (most permissive wins)
    3. Caches results in Redis (5-min TTL)
    4. Returns resolved PermissionSet for permission checking
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize permission service.
        
        Args:
            db_session: SQLAlchemy database session (tenant schema)
        """
        self.db_session = db_session
        self._redis_client = None
        self._initialize_redis()
    
    def _initialize_redis(self):
        """Initialize Redis client with connection pooling."""
        try:
            self._redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password if settings.redis_password else None,
                ssl=settings.redis_ssl,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self._redis_client.ping()
            logger.info("Redis connection established successfully")
        except redis.ConnectionError as e:
            logger.warning(f"Redis connection failed: {e}. Caching disabled.")
            self._redis_client = None
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}. Caching disabled.")
            self._redis_client = None
    
    def get_user_permissions(
        self,
        user_id: UUID,
        object_id: UUID,
        all_fields: List[str]
    ) -> PermissionSet:
        """
        Get complete permission set for user on an object.
        
        Args:
            user_id: User UUID
            object_id: Object UUID (from sys_object_metadata)
            all_fields: List of all field names in the object
            
        Returns:
            PermissionSet with resolved permissions
            
        Process:
        1. Check Redis cache
        2. If miss: Query database for all user roles
        3. Merge permissions from all roles
        4. Build field permission map
        5. Cache results for 5 minutes
        6. Return PermissionSet
        """
        cache_key = f"perms:{user_id}:{object_id}"
        
        # Try cache first
        if self._redis_client:
            try:
                cached = self._redis_client.get(cache_key)
                if cached:
                    logger.debug(f"Permission cache HIT for user {user_id} on object {object_id}")
                    permission_set = PermissionSet.from_dict(json.loads(cached))
                    return permission_set
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        
        logger.debug(f"Permission cache MISS for user {user_id} on object {object_id}")
        
        # Query database
        permission_set = self._resolve_permissions_from_db(user_id, object_id, all_fields)
        
        # Cache result
        if self._redis_client:
            try:
                self._redis_client.setex(
                    cache_key,
                    settings.permission_cache_ttl,
                    json.dumps(permission_set.to_dict())
                )
                logger.debug(f"Cached permissions for user {user_id} on object {object_id}")
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
        
        return permission_set
    
    def invalidate_user_permissions(self, user_id: UUID):
        """
        Invalidate all cached permissions for a user.
        
        Call this when user roles change.
        
        Args:
            user_id: User UUID
        """
        if not self._redis_client:
            return
        
        try:
            # Find all keys for this user
            pattern = f"perms:{user_id}:*"
            keys = self._redis_client.keys(pattern)
            if keys:
                self._redis_client.delete(*keys)
                logger.info(f"Invalidated {len(keys)} permission cache entries for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for user {user_id}: {e}")
    
    def invalidate_object_permissions(self, object_id: UUID):
        """
        Invalidate all cached permissions for an object.
        
        Call this when object permissions change.
        
        Args:
            object_id: Object UUID
        """
        if not self._redis_client:
            return
        
        try:
            # Find all keys for this object
            pattern = f"perms:*:{object_id}"
            keys = self._redis_client.keys(pattern)
            if keys:
                self._redis_client.delete(*keys)
                logger.info(f"Invalidated {len(keys)} permission cache entries for object {object_id}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for object {object_id}: {e}")
    
    def _resolve_permissions_from_db(
        self,
        user_id: UUID,
        object_id: UUID,
        all_fields: List[str]
    ) -> PermissionSet:
        """
        Query database and merge permissions from all user roles.
        
        Query Flow:
        1. sys_users → sys_user_roles (get all active role assignments)
        2. sys_user_roles → sys_roles (get role definitions)
        3. sys_roles → sys_object_permissions (get object-specific permissions)
        4. Merge all permissions (most permissive)
        
        Args:
            user_id: User UUID
            object_id: Object UUID
            all_fields: List of all field names
            
        Returns:
            PermissionSet
        """
        # Query all permission strings for user on this object
        query = text("""
            SELECT DISTINCT
                op.permissions,
                op.row_filter,
                op.field_permissions
            FROM sys_users u
            JOIN sys_user_roles ur ON u.id = ur.user_id
            JOIN sys_roles r ON ur.role_id = r.id
            LEFT JOIN sys_object_permissions op ON r.id = op.role_id
            WHERE u.user_id = :user_id
              AND ur.is_active = true
              AND r.is_active = true
              AND (op.object_id = :object_id OR op.object_id IS NULL)
              AND (op.is_active = true OR op.is_active IS NULL)
        """)
        
        result = self.db_session.execute(
            query,
            {"user_id": str(user_id), "object_id": str(object_id)}
        )
        
        # Merge permissions from all roles
        all_permissions: Set[str] = set()
        row_filters: List[str] = []
        field_perms_by_role: List[Dict] = []
        
        for row in result:
            # Merge permission arrays
            if row.permissions:
                perms = row.permissions if isinstance(row.permissions, list) else []
                all_permissions.update(perms)
            
            # Collect row filters
            if row.row_filter:
                row_filters.append(row.row_filter)
            
            # Collect field permissions
            if row.field_permissions:
                field_perms_by_role.append(row.field_permissions)
        
        # Convert to list
        merged_permissions = list(all_permissions)
        
        # Merge field permissions (use PermissionChecker to determine access)
        field_access = PermissionChecker.filter_fields(
            merged_permissions,
            all_fields
        )
        
        # Merge row filters (combine with OR)
        merged_row_filter = None
        if row_filters:
            # Combine filters with OR: (filter1) OR (filter2)
            merged_row_filter = " OR ".join([f"({f})" for f in row_filters])
        
        return PermissionSet(
            user_id=user_id,
            object_id=object_id,
            permissions=merged_permissions,
            field_permissions=field_access,
            row_filter=merged_row_filter
        )
    
    def get_user_scope(self, user_id: UUID, object_id: UUID, action: str = "read") -> Scope:
        """
        Get data scope for user on an object.
        
        Args:
            user_id: User UUID
            object_id: Object UUID
            action: Action to check (read, create, update, delete)
            
        Returns:
            Scope level
        """
        # Get permissions (will use cache if available)
        permission_set = self.get_user_permissions(user_id, object_id, [])
        
        # Use PermissionChecker to determine scope
        return PermissionChecker.get_data_scope(permission_set.permissions, action)
    
    def close(self):
        """Close Redis connection."""
        if self._redis_client:
            try:
                self._redis_client.close()
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")


# Singleton instance getter
_service_instance: Optional[PermissionService] = None


def get_permission_service(db_session: Session) -> PermissionService:
    """
    Get or create PermissionService instance.
    
    Args:
        db_session: SQLAlchemy database session
        
    Returns:
        PermissionService instance
    """
    # Note: In production, this should be request-scoped
    # For now, creating new instance per request to avoid session issues
    return PermissionService(db_session)
