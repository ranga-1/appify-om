"""JWT authentication middleware."""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)
security = HTTPBearer()


class UserContext(BaseModel):
    """User context extracted from JWT."""
    
    user_id: str  # sub claim
    user_role: str  # 'appify-admin' or 'customer-admin'
    customer_id: Optional[str] = None  # From groups for customer-admin
    customer_prefix: str  # From custom claim
    email: Optional[str] = None


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UserContext:
    """
    Extract user context from JWT token.
    
    Expected JWT structure:
    {
        "sub": "user-uuid",
        "email": "user@example.com",
        "groups": ["/customers/acme", "customer-admin"] or ["appify-admin"],
        "customer_prefix": "abc12"  # Custom claim
    }
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        UserContext with user information
        
    Raises:
        HTTPException: If token is invalid or missing required claims
    """
    token = credentials.credentials
    
    try:
        # Decode without verification (Keycloak already validated)
        # In production, add proper verification with public key
        payload = jwt.decode(
            token,
            key="",  # Empty key when not verifying signature
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_iss": False,
                "verify_exp": False
            }
        )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing sub claim"
            )
        
        # Extract groups
        groups = payload.get("groups", [])
        
        # Determine role and customer_id
        user_role = None
        customer_id = None
        
        # Check for appify-admin (with or without leading slash)
        if "appify-admin" in groups or "/appify-admin" in groups:
            user_role = "appify-admin"
            customer_id = "appify-admin"  # Set customer_id for appify-admin users
        else:
            # Look for customer-admin in groups
            if "customer-admin" in groups:
                user_role = "customer-admin"
                # Extract customer_id from groups like "/customers/acme"
                customer_groups = [
                    g for g in groups if g.startswith("/customers/")
                ]
                if customer_groups:
                    customer_id = customer_groups[0].split("/")[-1]
        
        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User must be appify-admin or customer-admin"
            )
        
        # Extract customer_prefix from custom claim (support both formats)
        customer_prefix = payload.get("customer_prefix") or payload.get("customer-prefix")
        if not customer_prefix:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing customer_prefix or customer-prefix claim"
            )
        
        logger.info(
            f"Authenticated user: {user_id}, role: {user_role}, "
            f"customer: {customer_id}, prefix: {customer_prefix}"
        )
        
        return UserContext(
            user_id=user_id,
            user_role=user_role,
            customer_id=customer_id,
            customer_prefix=customer_prefix.lower(),  # Ensure lowercase
            email=payload.get("email")
        )
        
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
