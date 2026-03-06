# Appify Object Modeler (appify-om)

Object metadata and dynamic data management service for Appify platform.

## Overview

The Object Modeler service manages metadata definitions for custom objects in a multi-tenant SaaS environment. It provides:

- **Tenant Schema Initialization**: Automatically provisions metadata tables in each tenant schema during tenant creation
- **Data Type Mappings**: Maintains mappings between database types and Object Modeler types
- **Object Metadata Registry**: Stores custom object definitions with fields, validations, and relationships

## Architecture

- **Internal Service**: Accessible only via ECS Service Discovery (no load balancer)
- **Multi-Tenant**: Uses schema-per-tenant pattern (e.g., `tenant_acme`, `tenant_xyz`)
- **Credential Caching**: Caches database credentials (default: 1 hour TTL)
- **Transactional**: All schema operations execute in transactions with automatic rollback on failure

## Deployment

For production deployment to AWS ECS, see [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

**Quick deployment:**
```bash
# 1. Create IAM role
./create-iam-task-role.sh

# 2. Get AWS resource IDs
./get-aws-resources.sh

# 3. Deploy to ECS
./deploy.sh
```

## Local Development Setup

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Run development server**:
   ```bash
   uv run python -m app.main
   ```

   Or with uvicorn directly:
   ```bash
   uv run uvicorn app.main:app --reload
   ```

## Tenant Schema Initialization

### SQL Files

Located in `sql/` directory:

1. **tenant-utility-functions.sql**: Creates trigger functions
   - `update_modified_date()`: Generic modified date updater
   - `update_object_metadata_modified_date()`: Specific to object metadata

2. **tenant-base-schema.sql**: Creates metadata tables
   - `sys_object_metadata`: Custom object definitions
   - `sys_om_datatype_mappings`: Database to OM type mappings

### Usage

The service automatically executes both SQL files in order when initializing a tenant schema. The tenant provisioning process calls this service after creating the tenant schema.

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Endpoints

#### POST /api/v1/tenants/{customer_id}/initialize-schema
Initialize Object Modeler metadata tables in a tenant schema.

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/tenants/acme/initialize-schema"
```

**Response:**
```json
{
  "success": true,
  "message": "Schema initialized successfully for customer: acme",
  "schema_name": "tenant_acme",
  "tables_created": [
    "sys_object_metadata",
    "sys_om_datatype_mappings"
  ],
  "functions_created": [
    "update_modified_date",
    "update_object_metadata_modified_date"
  ]
}
```

**Error Response:**
```json
{
  "detail": {
    "message": "Failed to initialize schema for customer: acme",
    "error": "Database error details...",
    "schema_name": "tenant_acme"
  }
}
```

#### GET /api/v1/tenants/{customer_id}/schema-status
Check if tenant schema has been initialized (not yet implemented).

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "appify-om",
  "version": "0.1.0",
  "environment": "development"
}
```

## Project Structure

```
appify-om/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI application
│   ├── config.py                    # Configuration management
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── tenants.py           # Tenant schema initialization endpoints
│   └── services/
│       ├── __init__.py
│       └── tenant_schema_init.py    # Tenant schema initialization service
├── sql/
│   ├── tenant-utility-functions.sql # Trigger functions
│   └── tenant-base-schema.sql       # Metadata table DDL
├── .env.example
├── .gitignore
└── pyproject.toml
```

## Configuration

Environment variables (via `.env` file):

```bash
# Service Configuration
API_VERSION=v1
LOG_LEVEL=INFO
ENVIRONMENT=development

# AWS Configuration
AWS_REGION=us-west-1
AWS_PROFILE=appify-unshackle

# Database Configuration
DB_SECRET_ID=appify/unshackle/identity/db
DB_NAME=tenants

# Credential Cache (seconds)
CREDENTIAL_CACHE_TTL=3600
```

## Development

- Python 3.11+
- FastAPI
- uv package manager
# appify-om
