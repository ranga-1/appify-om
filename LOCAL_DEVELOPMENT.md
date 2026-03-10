# Local Development Guide - appify-om

## Overview

Run the appify-om (Object Modeler) service locally on your machine while connecting to AWS RDS databases via SSH tunnel. This enables fast iteration without deploying to AWS.

## Prerequisites

- AWS CLI configured with `appify-unshackle` profile
- SSH key: `appify-unshackle/appify-bastion-key.pem`
- Python 3.11+
- UV package manager
- Network connectivity to AWS

## Quick Start

### 1. Start SSH Tunnel (Terminal 1)
```bash
cd /Users/rangavaithyalingam/Projects/appify-unshackle
./setup-local-dev.sh
# Keep this terminal running
```

### 2. Run OM Service (Terminal 2)
```bash
cd /Users/rangavaithyalingam/Projects/appify-om
./run-local.sh
```

The service will start on http://localhost:8000

### 3. Verify Service
```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

# API docs
open http://localhost:8000/docs
```

## Architecture

**Local Service:**
- Port: 8000
- Hot reload: Enabled (uvicorn --reload)

**Remote Dependencies (AWS):**
- Tenants DB: `tenants` via SSH tunnel (localhost:5434 → RDS:5432)
  - User: `tenant_admin`
- Core DB: `unshackle_core` via SSH tunnel (localhost:5434 → RDS:5432)
  - User: `unshackle_core`

## Configuration

### Local Mode (.env.local)
```bash
USE_LOCAL_CREDENTIALS=true  # Read from environment variables

# Tenants database
TENANTS_DB_HOST=localhost
TENANTS_DB_PORT=5434
TENANTS_DB_NAME=tenants
TENANTS_DB_USERNAME=tenant_admin
TENANTS_DB_PASSWORD=<from .env.local>

# Core database
CORE_DB_HOST=localhost
CORE_DB_PORT=5434
CORE_DB_NAME=unshackle_core
CORE_DB_USERNAME=unshackle_core
CORE_DB_PASSWORD=<from .env.local>
```

### Production Mode (.env.production)
```bash
USE_LOCAL_CREDENTIALS=false  # Read from AWS Secrets Manager
DB_SECRET_ID=appify/unshackle/tenants/admin
CORE_DB_SECRET_ID=appify/unshackle/core/db
```

## Development Workflow

1. **Make code changes** - Files are automatically reloaded
2. **Test locally** - Use curl, Postman, or API docs
3. **Check logs** - Displayed in terminal (DEBUG level)
4. **Commit changes** - When tests pass
5. **Deploy to AWS** - When ready for production

## Testing

### Object Metadata Operations

**Note**: Requires authentication token from appify-identity service

```bash
# Get token from identity service
TOKEN="<access_token_from_identity_login>"

# Create object metadata
curl -X POST http://localhost:8000/api/v1/object-metadata \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "Customer",
    "description": "Customer information",
    "fields": [
      {
        "field_name": "name",
        "data_type": "string",
        "description": "Customer name"
      }
    ]
  }'

# List object metadata
curl http://localhost:8000/api/v1/object-metadata \
  -H "Authorization: Bearer $TOKEN"

# Get specific object
curl http://localhost:8000/api/v1/object-metadata/{object_id} \
  -H "Authorization: Bearer $TOKEN"

# Update object metadata
curl -X PUT http://localhost:8000/api/v1/object-metadata/{object_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "Customer Account",
    "description": "Updated description"
  }'

# Deploy object (creates database table)
curl -X POST http://localhost:8000/api/v1/object-metadata/{object_id}/deploy \
  -H "Authorization: Bearer $TOKEN"
```

### Database Verification

```bash
# Connect to tenant database
psql -h localhost -p 5434 -U tenant_admin -d tenants

# Check object metadata
SELECT id, api_name, label, status FROM tenant_{customer_id}.sys_object_metadata;

# Check deployed table
\d tenant_{customer_id}.{api_name}
```

## Troubleshooting

### Cannot connect to database
**Symptom**: Connection refused to localhost:5434

**Solutions**:
- Check SSH tunnel: `nc -z localhost 5434`
- Restart tunnel: `cd ../appify-unshackle && ./start-bastion-tunnel.sh`
- Verify bastion host is running in AWS

### Module not found errors
**Symptom**: ImportError or ModuleNotFoundError

**Solutions**:
- Reinstall dependencies: `source .venv/bin/activate && uv pip install -e .`
- Delete .venv and recreate: `rm -rf .venv && ./run-local.sh`

### Dual database connection issues
**Symptom**: Can connect to one database but not the other

**Solutions**:
- Verify both databases use same SSH tunnel (port 5434)
- Check credentials in .env.local for both databases
- Test connection manually:
  ```bash
  psql -h localhost -p 5434 -U tenant_admin -d tenants -c '\dt'
  psql -h localhost -p 5434 -U unshackle_core -d unshackle_core -c '\dt'
  ```

### Authentication failures
**Symptom**: 401 Unauthorized errors

**Solutions**:
- Ensure appify-identity service is running: `curl http://localhost:8001/health`
- Get fresh token from identity service
- Check token expiration

### Configuration not loading
**Symptom**: Using wrong database or credentials

**Solutions**:
- Verify .env file: `cat .env | grep USE_LOCAL_CREDENTIALS`
- Should show: `USE_LOCAL_CREDENTIALS=true`
- If not, run script again: `./run-local.sh`

## Deployment (After Local Testing)

When ready to deploy to AWS:

```bash
# Stop local service (Ctrl+C)

# Run deployment script
./deploy.sh
```

The deployment script will:
- Build Docker image
- Push to ECR
- Register new task definition  
- Update ECS service
- Use .env.production settings (Secrets Manager)

## File Reference

- `.env.local` - Local development config (with credentials)
- `.env.production` - Production config (Secrets Manager references)
- `run-local.sh` - Local startup script
- `LOCAL_DEVELOPMENT.md` - This file

## Security Notes

⚠️ **NEVER commit .env.local or .env.production** - They contain sensitive credentials

✓ Both files are in .gitignore

✓ Credentials are only stored locally on your machine

✓ AWS deployments use Secrets Manager (no hardcoded credentials)
