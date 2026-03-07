"""Object Metadata REST API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.middleware.auth import UserContext, get_current_user
from app.models.object_metadata import (
    ObjectMetadataCreate,
    ObjectMetadataListResponse,
    ObjectMetadataResponse,
    ObjectMetadataUpdate,
    ObjectDeploymentResponse
)
from app.services.object_metadata_service import ObjectMetadataService
from app.services.object_deployment_service import ObjectDeploymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/object-metadata", tags=["object-metadata"])
service = ObjectMetadataService()
deployment_service = ObjectDeploymentService()


@router.get(
    "",
    response_model=ObjectMetadataListResponse,
    summary="List all business objects",
    description="""
    Get paginated list of business objects (object metadata).
    
    - **appify-admin**: Retrieves from unshackle_core.public schema
    - **customer-admin**: Retrieves from tenants.tenant_{customer_id} schema
    """
)
def list_object_metadata(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    user: UserContext = Depends(get_current_user)
):
    """Get paginated list of object metadata."""
    try:
        items, total = service.get_all(
            user_role=user.user_role,
            customer_id=user.customer_id,
            skip=skip,
            limit=limit
        )
        
        return ObjectMetadataListResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit
        )
        
    except Exception as e:
        logger.exception("Error listing object metadata")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/{object_id}",
    response_model=ObjectMetadataResponse,
    summary="Get business object by ID",
    description="Retrieve a single business object by its UUID."
)
def get_object_metadata(
    object_id: UUID,
    user: UserContext = Depends(get_current_user)
):
    """Get single object metadata by ID."""
    try:
        result = service.get_by_id(
            object_id=object_id,
            user_role=user.user_role,
            customer_id=user.customer_id
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object with id {object_id} not found"
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting object metadata")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "",
    response_model=ObjectMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new business object",
    description="""
    Create a new business object.
    
    The API name is automatically generated from the label:
    - Label: "Customer Account" → API Name: "{prefix}_customer_account"
    - Prefix is extracted from the user's JWT token (customer prefix attribute)
    
    The API name must be unique within the schema.
    """
)
def create_object_metadata(
    data: ObjectMetadataCreate,
    user: UserContext = Depends(get_current_user)
):
    """Create new object metadata."""
    try:
        result = service.create(
            data=data,
            user_id=user.user_id,
            user_role=user.user_role,
            customer_id=user.customer_id,
            customer_prefix=user.customer_prefix
        )
        
        logger.info(
            f"Object created: {result.api_name} by user {user.user_id}"
        )
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Error creating object metadata")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put(
    "/{object_id}",
    response_model=ObjectMetadataResponse,
    summary="Update business object",
    description="""
    Update an existing business object.
    
    If the label is changed, the API name is automatically regenerated
    using the customer's prefix.
    """
)
def update_object_metadata(
    object_id: UUID,
    data: ObjectMetadataUpdate,
    user: UserContext = Depends(get_current_user)
):
    """Update existing object metadata."""
    try:
        result = service.update(
            object_id=object_id,
            data=data,
            user_id=user.user_id,
            user_role=user.user_role,
            customer_id=user.customer_id,
            customer_prefix=user.customer_prefix
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object with id {object_id} not found"
            )
        
        logger.info(
            f"Object updated: {result.api_name} by user {user.user_id}"
        )
        return result
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Error updating object metadata")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/{object_id}/deploy",
    response_model=ObjectDeploymentResponse,
    summary="Deploy business object as database table",
    description="""
    Deploy an object metadata definition as a physical database table.
    
    **Requirements:**
    - Object status must be 'draft' or 'failed'
    - Object must have valid fields array
    - All referenced objects (in Reference fields) must already exist as tables
    - API names must be unique
    
    **Process:**
    1. Validates object and fields
    2. Sets status to 'deploying'
    3. Creates table with system fields (id, created_by, modified_by, created_date, modified_date, audit_info)
    4. Creates user-defined fields with prefix (e.g., abc12_email)
    5. Adds column comments
    6. Creates UNIQUE constraints
    7. Creates FOREIGN KEY constraints (ON DELETE RESTRICT)
    8. Creates indexes on created_date, modified_date, unique fields, and foreign keys
    9. Sets status to 'created' or 'failed'
    
    **Retry:**
    - If deployment fails (status='failed'), you can retry by updating status to 'draft' and calling deploy again
    
    **Schema Routing:**
    - **appify-admin**: Creates table in unshackle_core.public
    - **customer-admin**: Creates table in tenants.tenant_{customer_id}
    """
)
def deploy_object_metadata(
    object_id: UUID,
    user: UserContext = Depends(get_current_user)
):
    """Deploy object metadata as database table."""
    try:
        result = deployment_service.deploy_object(
            object_id=object_id,
            user_role=user.user_role,
            customer_id=user.customer_id
        )
        
        logger.info(
            f"Object deployed: {result['api_name']} → {result['table_name']} "
            f"in {result['schema']} by user {user.user_id}"
        )
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error deploying object {object_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
