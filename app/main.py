"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings
from app.api.v1 import tenants, object_metadata, datatype_mappings, data, admin

# Configure logging
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Appify Object Modeler API",
    description="Object metadata and dynamic data management service",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(tenants.router, prefix=f"/api/{settings.api_version}")
app.include_router(object_metadata.router, prefix=f"/api/{settings.api_version}")
app.include_router(datatype_mappings.router, prefix=f"/api/{settings.api_version}")
app.include_router(data.router, prefix=f"/api/{settings.api_version}")  # Generic Data API
app.include_router(admin.router, prefix=f"/api/{settings.api_version}")  # Phase 4: Audit & Soft Delete


@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    logger.info("=" * 60)
    logger.info("Appify Object Modeler Service Starting")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"API Version: {settings.api_version}")
    logger.info(f"Log Level: {settings.log_level}")
    logger.info(f"AWS Region: {settings.aws_region}")
    logger.info(f"Database: {settings.db_name}")
    logger.info(f"Credential Cache TTL: {settings.credential_cache_ttl}s")
    logger.info("=" * 60)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "appify-om",
        "version": "0.1.0",
        "environment": settings.environment
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Appify Object Modeler API",
        "version": "0.1.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower()
    )
