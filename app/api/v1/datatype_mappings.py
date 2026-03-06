"""API routes for Datatype Mappings."""

import logging
from typing import List

from fastapi import APIRouter, Depends

from app.middleware.auth import UserContext, get_current_user
from app.models.datatype_mapping import DatatypeMappingResponse
from app.services.datatype_mapping_service import DatatypeMappingService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/datatype-mappings", tags=["Datatype Mappings"])
service = DatatypeMappingService()


@router.get("", response_model=List[DatatypeMappingResponse])
async def get_all_datatype_mappings(
    user: UserContext = Depends(get_current_user)
):
    """
    Get all datatype mappings.
    
    Returns list of available datatypes with their properties schema.
    Used by Object Modeler UI to render field creation forms.
    """
    logger.info(
        f"Fetching datatype mappings for user {user.user_id} "
        f"(role: {user.user_role})"
    )
    
    items = service.get_all(
        user_role=user.user_role,
        customer_id=user.customer_id
    )
    
    return items
