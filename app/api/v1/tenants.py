"""Tenant-related API endpoints for Object Modeler service."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.tenant_schema_init import get_tenant_schema_initializer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])


# Request Models
class AdminUserInfo(BaseModel):
    """Admin user information for tenant provisioning."""
    
    user_id: str = Field(..., description="Keycloak user UUID")
    email: str = Field(..., description="Admin user email address")
    username: str = Field(..., description="Admin username")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    full_name: Optional[str] = Field(None, description="Full name")
    role_type: str = Field("customer_admin", description="Role to assign (customer_admin or customer_user)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "email": "admin@acme.com",
                "username": "admin@acme.com",
                "first_name": "John",
                "last_name": "Doe",
                "full_name": "John Doe",
                "role_type": "customer_admin"
            }
        }


class TenantSchemaInitRequest(BaseModel):
    """Request model for tenant schema initialization."""
    
    username: str = Field(..., description="Database username for the tenant")
    password: str = Field(..., description="Database password for the tenant")
    admin_user: Optional[AdminUserInfo] = Field(None, description="Optional admin user to create during provisioning")
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "tenant_acme",
                "password": "secure_password_123",
                "admin_user": {
                    "user_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "email": "admin@acme.com",
                    "username": "admin@acme.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "full_name": "John Doe",
                    "role_type": "customer_admin"
                }
            }
        }


# Response Models
class TenantSchemaInitResponse(BaseModel):
    """Response model for tenant schema initialization."""
    
    success: bool = Field(..., description="Whether initialization succeeded")
    message: str = Field(..., description="Human-readable status message")
    schema_name: str = Field(..., description="Name of the tenant schema")
    tables_created: Optional[List[str]] = Field(
        None, 
        description="List of tables created (if successful)"
    )
    functions_created: Optional[List[str]] = Field(
        None,
        description="List of functions created (if successful)"
    )
    error: Optional[str] = Field(
        None, 
        description="Error details (if failed)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Schema initialized successfully for customer: acme",
                "schema_name": "tenant_acme",
                "tables_created": ["sys_object_metadata", "sys_om_datatype_mappings", "sys_users"],
                "functions_created": ["update_modified_date", "update_object_metadata_modified_date"]
            }
        }


@router.post(
    "/{customer_id}/initialize-schema",
    response_model=TenantSchemaInitResponse,
    status_code=status.HTTP_200_OK,
    summary="Initialize tenant schema with OM metadata tables",
    description="""
    Initialize Object Modeler metadata tables in a tenant schema.
    
    This endpoint is called by the identity service during tenant provisioning
    to create the base metadata tables in the new tenant's schema.
    
    **Internal Use Only** - This endpoint is not exposed via load balancer.
    It's accessible only through ECS Service Discovery.
    
    The operation is transactional - if any step fails, all changes are 
    automatically rolled back.
    
    ## What Gets Created:
    
    1. **Utility Functions**:
       - `update_modified_date()`: Generic trigger function for modified_date
       - `update_object_metadata_modified_date()`: Specific to sys_object_metadata
    
    2. **Metadata Tables**:
       - `sys_object_metadata`: Custom object definitions with fields, validations, relationships, and deployment tracking (status, table creation dates)
       - `sys_om_datatype_mappings`: Database to OM data type mappings
       - `sys_users`: User information synchronized from Keycloak with extended profile data
    
    ## sys_object_metadata Deployment Workflow:
    
    - Objects start in 'draft' status and can be edited
    - When user clicks "Deploy", status changes to 'deploying'
    - On success: status='created', table_created_date set, table_name recorded
    - On failure: status='failed', deployment_error captured for troubleshooting
    
    ## Error Handling:
    
    - Database errors: Returns HTTP 500 with error details
    - Missing SQL files: Returns HTTP 500 with file path
    - Any failure triggers automatic transaction rollback
    """
)
def initialize_tenant_schema(
    customer_id: str,
    request: TenantSchemaInitRequest
) -> TenantSchemaInitResponse:
    """Initialize Object Modeler metadata tables in tenant schema.
    
    Args:
        customer_id: Customer ID for the tenant (e.g., 'acme', 'xyz')
        request: Request containing username and password
        
    Returns:
        TenantSchemaInitResponse with success status and details
        
    Raises:
        HTTPException: 500 if initialization fails
    """
    try:
        logger.info(f"Received schema initialization request for customer: {customer_id}")
        logger.info(f"Username: {request.username}")
        if request.admin_user:
            logger.info(f"Admin user to create: {request.admin_user.email} (role: {request.admin_user.role_type})")
        
        # Get the initializer service
        initializer = get_tenant_schema_initializer()
        
        # Initialize the tenant schema
        result = initializer.initialize_tenant_schema(
            customer_id, 
            request.username, 
            request.password,
            admin_user=request.admin_user.dict() if request.admin_user else None
        )
        
        if not result["success"]:
            # Initialization failed but didn't raise exception
            logger.error(f"Schema initialization failed for {customer_id}: {result.get('error')}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": result["message"],
                    "error": result.get("error"),
                    "schema_name": result["schema_name"]
                }
            )
        
        logger.info(f"Successfully initialized schema for customer: {customer_id}")
        return TenantSchemaInitResponse(**result)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        # Catch any unexpected errors
        logger.exception(f"Unexpected error during schema initialization for {customer_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"Failed to initialize schema for customer: {customer_id}",
                "error": str(e),
                "schema_name": f"tenant_{customer_id}"
            }
        )


@router.get(
    "/{customer_id}/schema-status",
    summary="Check tenant schema status",
    description="""
    Check if Object Modeler metadata tables exist in a tenant schema.
    
    **Internal Use Only** - Accessible only through ECS Service Discovery.
    
    This endpoint can be used to verify if a tenant schema has been properly
    initialized with OM metadata tables.
    """
)
def check_schema_status(customer_id: str):
    """Check if tenant schema has been initialized with OM tables.
    
    Args:
        customer_id: Customer ID for the tenant
        
    Returns:
        Status information about the tenant schema
    """
    # TODO: Implement schema status check
    # This would query the tenant schema to see if tables exist
    return {
        "customer_id": customer_id,
        "schema_name": f"tenant_{customer_id}",
        "status": "not_implemented",
        "message": "Schema status check not yet implemented"
    }
