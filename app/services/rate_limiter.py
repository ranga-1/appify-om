"""Rate limiting service using Redis."""

from typing import Optional, Tuple
from fastapi import HTTPException, status
import redis
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiting service using Redis.
    
    Implements sliding window rate limiting with different limits
    for different endpoint types.
    
    Features:
    - Per-user rate limits
    - Per-tenant rate limits
    - Different limits for different operations
    - Returns rate limit headers
    """
    
    # Rate limits (requests per hour)
    LIMITS = {
        "crud": 1000,  # CRUD operations
        "bulk": 100,   # Bulk operations
        "export": 10,  # Export operations
        "import": 10,  # Import operations
        "query": 500,  # Query operations
        "aggregate": 200,  # Aggregation queries
    }
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize rate limiter.
        
        Args:
            redis_client: Redis client instance (optional)
        """
        self.redis = redis_client
        if not self.redis:
            # Create default Redis connection
            try:
                from app.config import settings
                self.redis = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                self.redis.ping()
                logger.info("Redis connection established for rate limiting")
            except Exception as e:
                logger.warning(f"Redis not available, rate limiting disabled: {e}")
                self.redis = None
    
    def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int = 3600
    ) -> Tuple[bool, int, int, int]:
        """
        Check if rate limit is exceeded.
        
        Args:
            key: Unique key for this rate limit (e.g., "user:123:crud")
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (allowed, remaining, reset_timestamp, total_requests)
        """
        if not self.redis:
            # Rate limiting disabled
            return True, limit, int(datetime.now().timestamp()) + window_seconds, 0
        
        try:
            now = datetime.now()
            window_start = now - timedelta(seconds=window_seconds)
            
            # Use sorted set with timestamps as scores
            pipe = self.redis.pipeline()
            
            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start.timestamp())
            
            # Count requests in current window
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(now.timestamp()): now.timestamp()})
            
            # Set expiry on the key
            pipe.expire(key, window_seconds)
            
            # Execute pipeline
            _, count, _, _ = pipe.execute()
            
            # Check if limit exceeded
            allowed = count < limit
            remaining = max(0, limit - count)
            reset_time = int(now.timestamp()) + window_seconds
            
            return allowed, remaining, reset_time, count
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}", exc_info=True)
            # Fail open - allow request if Redis is down
            return True, limit, int(datetime.now().timestamp()) + window_seconds, 0
    
    def check_user_rate_limit(
        self,
        user_id: str,
        operation_type: str
    ) -> Tuple[bool, dict]:
        """
        Check rate limit for a user operation.
        
        Args:
            user_id: User identifier
            operation_type: Type of operation (crud, bulk, export, etc.)
            
        Returns:
            Tuple of (allowed, headers dict)
        """
        limit = self.LIMITS.get(operation_type, self.LIMITS["crud"])
        key = f"ratelimit:user:{user_id}:{operation_type}"
        
        allowed, remaining, reset_time, total = self.check_rate_limit(key, limit)
        
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
            "X-RateLimit-Used": str(total)
        }
        
        if not allowed:
            headers["Retry-After"] = str(reset_time - int(datetime.now().timestamp()))
        
        return allowed, headers
    
    def check_tenant_rate_limit(
        self,
        tenant_id: str,
        operation_type: str
    ) -> Tuple[bool, dict]:
        """
        Check rate limit for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            operation_type: Type of operation
            
        Returns:
            Tuple of (allowed, headers dict)
        """
        # Tenant limits are 10x user limits
        limit = self.LIMITS.get(operation_type, self.LIMITS["crud"]) * 10
        key = f"ratelimit:tenant:{tenant_id}:{operation_type}"
        
        allowed, remaining, reset_time, total = self.check_rate_limit(key, limit)
        
        headers = {
            "X-Tenant-RateLimit-Limit": str(limit),
            "X-Tenant-RateLimit-Remaining": str(remaining),
            "X-Tenant-RateLimit-Reset": str(reset_time)
        }
        
        return allowed, headers
    
    def enforce_rate_limit(
        self,
        user_id: str,
        tenant_id: str,
        operation_type: str
    ) -> dict:
        """
        Enforce rate limits for both user and tenant.
        
        Raises HTTPException if limit exceeded.
        
        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            operation_type: Type of operation
            
        Returns:
            Headers dict to include in response
        """
        # Check user rate limit
        user_allowed, user_headers = self.check_user_rate_limit(user_id, operation_type)
        
        if not user_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {operation_type} operations. Try again in {user_headers.get('Retry-After', 'a few')} seconds.",
                headers=user_headers
            )
        
        # Check tenant rate limit
        tenant_allowed, tenant_headers = self.check_tenant_rate_limit(tenant_id, operation_type)
        
        if not tenant_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Tenant rate limit exceeded for {operation_type} operations.",
                headers=tenant_headers
            )
        
        # Merge headers
        return {**user_headers, **tenant_headers}
    
    def get_usage_stats(
        self,
        user_id: str,
        operation_type: Optional[str] = None
    ) -> dict:
        """
        Get rate limit usage statistics for a user.
        
        Args:
            user_id: User identifier
            operation_type: Specific operation type, or all if None
            
        Returns:
            Usage statistics
        """
        if not self.redis:
            return {}
        
        stats = {}
        
        op_types = [operation_type] if operation_type else self.LIMITS.keys()
        
        for op_type in op_types:
            limit = self.LIMITS.get(op_type, self.LIMITS["crud"])
            key = f"ratelimit:user:{user_id}:{op_type}"
            
            try:
                count = self.redis.zcard(key)
                ttl = self.redis.ttl(key)
                
                stats[op_type] = {
                    "limit": limit,
                    "used": count,
                    "remaining": max(0, limit - count),
                    "resets_in_seconds": ttl if ttl > 0 else 3600
                }
            except Exception as e:
                logger.error(f"Error getting usage stats: {e}")
        
        return stats


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """
    Get or create global rate limiter instance.
    
    Usage in FastAPI:
        rate_limiter = Depends(get_rate_limiter)
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
