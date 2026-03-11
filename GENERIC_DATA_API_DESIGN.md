# Generic Data API - Complete Design Document

**Version:** 1.0  
**Date:** March 10, 2026  
**Author:** System Architecture  
**Status:** Design Phase

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [IAM-Style Permission Model](#3-iam-style-permission-model)
4. [API Design](#4-api-design)
5. [Permission Enforcement](#5-permission-enforcement)
6. [Query & Filter System](#6-query--filter-system)
7. [Bulk Operations](#7-bulk-operations)
8. [Caching Strategy](#8-caching-strategy)
9. [Security](#9-security)
10. [Performance & Scalability](#10-performance--scalability)
11. [Implementation Plan](#11-implementation-plan)
12. [Appendices](#12-appendices)

---

## 1. Executive Summary

### 1.1 Purpose

This document defines the architecture and implementation strategy for a **Generic Data API** that provides CRUD operations, bulk processing, and advanced querying capabilities for dynamically-created database tables based on Object Metadata.

### 1.2 Key Requirements

- **Multi-tenant isolation**: Each customer's data isolated in separate schemas
- **Dynamic table access**: Tables created from Object Metadata definitions
- **Granular permissions**: IAM-style permissions for fine-grained access control
- **High performance**: Support millions of records with sophisticated queries
- **Bulk operations**: Handle large-scale imports/exports asynchronously
- **API versioning**: Support multiple API versions simultaneously
- **Security**: SQL injection prevention, field-level security, audit trails

### 1.3 Design Principles

1. **Security First**: Fail-closed permissions, defense in depth
2. **Performance**: Caching, pagination, read replicas
3. **Extensibility**: IAM-style permissions support unlimited capability expansion
4. **Developer-Friendly**: RESTful + RPC hybrid, self-documenting permissions
5. **Scalability**: Horizontal scaling, async bulk processing

---

## 2. Architecture Overview

### 2.1 System Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway Layer                         │
│  - JWT Token Validation                                      │
│  - Rate Limiting (Redis)                                     │
│  - Request ID Generation                                     │
│  - Audit Logging                                             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                 Permission Resolution Layer                  │
│  - Load User Roles from Keycloak                            │
│  - Load Object Permissions from Database                     │
│  - Merge Permissions (most permissive wins)                 │
│  - Cache in Redis (5-min TTL)                                │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  Data Service Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Sync API   │  │  Async Jobs  │  │   Query API  │      │
│  │   (CRUD)     │  │   (Bulk)     │  │  (Advanced)  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                  │               │
│  ┌──────▼─────────────────▼──────────────────▼───────┐      │
│  │         Generic Data Repository                    │      │
│  │  - Query Builder (safe SQL generation)             │      │
│  │  - Permission Enforcement (row/field level)        │      │
│  │  - Audit Trail Logging                             │      │
│  └──────────────────────┬──────────────────────────────┘      │
└─────────────────────────┼────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────┐
│                   Database Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Primary    │  │  Read Rep 1  │  │  Read Rep 2  │      │
│  │   (Writes)   │  │   (Reads)    │  │   (Reads)    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  Tenant Schemas: tenant_{id}.{table_name}                   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| API Framework | FastAPI (Python) | Async, type hints, auto-docs |
| Database | PostgreSQL 15+ | JSONB, strong consistency, mature |
| Cache | Redis 7+ | Pub/sub, TTL, atomic operations |
| Job Queue | Redis (Bull/Celery) | Simple, reliable, ordered processing |
| Auth | Keycloak | OAuth2, RBAC, SSO support |
| Load Balancer | AWS ALB | Auto-scaling, health checks |
| Connection Pool | PgBouncer | Connection reuse, reduces DB load |

### 2.3 Data Flow

**Synchronous Request (Single Record):**
```
Client → ALB → API Gateway → Permission Check → Query Builder → DB → Response
         ↓
      Audit Log (async)
```

**Asynchronous Request (Bulk):**
```
Client → ALB → API Gateway → Permission Check → Job Queue → 202 Accepted
                                                     ↓
                                              Worker Pool → DB (batched)
                                                     ↓
                                              Job Status Update
         
Client polls: GET /jobs/{id} → Job Status
```

---

## 3. IAM-Style Permission Model

### 3.1 Permission String Format

```
{resource}:{action}[:{modifier}[:{value}]]
```

**Components:**
- **resource**: What you're accessing (data, bulk, query, schema, admin)
- **action**: What you're doing (read, write, delete, execute)
- **modifier**: Optional constraint (scope, format, depth)
- **value**: Optional parameter (self, team, all, csv, 2)

### 3.2 Permission Catalog

#### **Data Operations**
```
data:create                        # Create new records
data:read                          # Read records
data:read:scope:self              # Read only own records
data:read:scope:team              # Read team records
data:read:scope:all               # Read all tenant records
data:update                        # Update records
data:update:scope:self            # Update only own records
data:delete                        # Soft delete records
data:delete:permanent             # Hard delete (admin only)
data:restore                       # Restore soft-deleted records
data:*                            # All data operations
```

#### **Bulk Operations**
```
bulk:import                        # Bulk create/upsert
bulk:import:limit:10000           # Max 10K records/job
bulk:update                        # Bulk update
bulk:delete                        # Bulk soft delete
bulk:export                        # Export data
bulk:export:format:csv            # Export CSV only
bulk:export:format:excel          # Export Excel only
bulk:export:format:json           # Export JSON only
bulk:export:format:*              # Export any format
bulk:*                            # All bulk operations
```

#### **Query Operations**
```
query:basic                        # Simple filters (=, !=, IN)
query:advanced                     # Complex (LIKE, ranges, OR)
query:aggregation                  # COUNT, SUM, AVG, GROUP BY
query:aggregation:function:count  # COUNT only
query:composite                    # Nested/chained queries
query:composite:depth:2           # Max 2 nesting levels
query:sql                          # Raw SQL (dangerous!)
query:*                           # All query types
```

#### **Field-Level Permissions**
```
field:read:{field_api_name}       # Read specific field
field:write:{field_api_name}      # Write specific field
field:mask:{field_api_name}       # Show masked (****)
field:hide:{field_api_name}       # Hide completely
field:*                           # All fields accessible
```

#### **Schema Operations**
```
schema:read                        # View object metadata
schema:create                      # Create new objects
schema:modify                      # Modify metadata
schema:deploy                      # Deploy (create tables)
schema:delete                      # Delete objects
schema:*                          # All schema operations
```

#### **Admin Operations**
```
admin:permissions:read            # View permissions
admin:permissions:grant           # Grant permissions
admin:permissions:revoke          # Revoke permissions
admin:audit:read                  # View audit logs
admin:users:impersonate          # Impersonate users
admin:*                          # All admin operations
```

### 3.3 Permission Storage

**Database Schema:**
```sql
CREATE TABLE sys_object_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_id UUID NOT NULL REFERENCES sys_object_metadata(id),
    role_id UUID NOT NULL,  -- Keycloak role ID
    permissions JSONB NOT NULL,  -- Array of permission strings
    row_filter TEXT,  -- SQL WHERE clause for row-level security
    created_by UUID NOT NULL,
    created_date TIMESTAMP NOT NULL DEFAULT now(),
    modified_by UUID NOT NULL,
    modified_date TIMESTAMP NOT NULL DEFAULT now(),
    
    CONSTRAINT unique_object_role UNIQUE (object_id, role_id),
    CONSTRAINT valid_permissions CHECK (jsonb_typeof(permissions) = 'array')
);

CREATE INDEX idx_object_permissions_object ON sys_object_permissions(object_id);
CREATE INDEX idx_object_permissions_role ON sys_object_permissions(role_id);
CREATE INDEX idx_object_permissions_perms ON sys_object_permissions USING gin(permissions);
```

**Example Record:**
```json
{
    "object_id": "uuid-of-customer-account",
    "role_id": "uuid-of-sales-role",
    "permissions": [
        "data:read:scope:all",
        "data:create",
        "data:update:scope:self",
        "query:advanced",
        "bulk:export:format:csv",
        "field:read:*",
        "field:write:abc12_status",
        "field:mask:abc12_salary",
        "field:hide:abc12_ssn"
    ],
    "row_filter": "abc12_department = 'Sales' OR created_by = $user_id"
}
```

### 3.4 Permission Resolution Rules

**When user has multiple roles:**

1. **Merge all permissions** from all roles
2. **Most permissive wins** for scope hierarchy: `global > all > team > self`
3. **Wildcard expansion**: `data:*` includes all data operations
4. **Field-level override**: Specific field permissions override wildcards

**Example:**
```python
# User roles: [sales_rep, data_analyst]
# sales_rep: ["data:read:scope:team", "data:create"]
# data_analyst: ["data:read:scope:all", "query:advanced"]

# MERGED RESULT:
[
    "data:read:scope:all",     # 'all' > 'team'
    "data:create",             # From sales_rep
    "query:advanced"           # From data_analyst
]
```

---

## 4. API Design

### 4.1 URL Structure

**Base Pattern:**
```
/api/v{version}/data/{tenant_id}/{object_api_name}/{operation}
```

**Versioning Strategy:**
- **Major version** in URL: `/api/v1/`, `/api/v2/`
- **Minor version** in header: `X-API-Version: 1.2`
- **Deprecation policy**: Support N-1 major versions (12-month notice)

### 4.2 Single-Record Operations (Synchronous)

#### **CREATE**
```http
POST /api/v1/data/tenant_abc/abc12_customer_account
Authorization: Bearer {jwt_token}
Content-Type: application/json

Request Body:
{
    "abc12_email": "john@example.com",
    "abc12_first_name": "John",
    "abc12_last_name": "Doe",
    "abc12_status": "active"
}

Response 201 Created:
{
    "status": "success",
    "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "abc12_email": "john@example.com",
        "abc12_first_name": "John",
        "abc12_last_name": "Doe",
        "abc12_status": "active",
        "created_by": "user-uuid",
        "created_date": "2026-03-10T10:30:00Z",
        "modified_by": "user-uuid",
        "modified_date": "2026-03-10T10:30:00Z",
        "is_deleted": false
    },
    "metadata": {
        "api_version": "1.0",
        "request_id": "req-uuid",
        "timestamp": "2026-03-10T10:30:00Z"
    }
}
```

**Required Permission:** `data:create`

---

#### **READ (Single)**
```http
GET /api/v1/data/tenant_abc/abc12_customer_account/{id}

Response 200 OK:
{
    "status": "success",
    "data": { ... }
}
```

**Required Permission:** `data:read` (+ scope enforcement)

---

#### **UPDATE**
```http
PUT /api/v1/data/tenant_abc/abc12_customer_account/{id}

Request Body:
{
    "abc12_status": "inactive",
    "abc12_last_name": "Smith"
}

Response 200 OK:
{
    "status": "success",
    "data": { ... }
}
```

**Required Permission:** `data:update` (+ scope + field-level)

---

#### **DELETE (Soft)**
```http
DELETE /api/v1/data/tenant_abc/abc12_customer_account/{id}

Response 200 OK:
{
    "status": "success",
    "data": {
        "id": "uuid",
        "is_deleted": true,
        "deleted_by": "user-uuid",
        "deleted_date": "2026-03-10T11:30:00Z"
    }
}
```

**Required Permission:** `data:delete`

---

#### **DELETE (Permanent)**
```http
DELETE /api/v1/data/tenant_abc/abc12_customer_account/{id}?permanent=true

Response 204 No Content
```

**Required Permission:** `data:delete:permanent` (admin only)

---

### 4.3 Query Operations

#### **LIST with Pagination**
```http
GET /api/v1/data/tenant_abc/abc12_customer_account?limit=100&cursor={cursor}

Response 200 OK:
{
    "status": "success",
    "data": [ ... ],
    "pagination": {
        "next_cursor": "eyJsYXN0X2lkIjoi...",
        "prev_cursor": "eyJsYXN0X2lkIjoi...",
        "has_more": true,
        "limit": 100,
        "total_estimate": 4500000
    }
}
```

**Query Parameters:**
- `limit`: Max records (default 100, max 1000)
- `cursor`: Base64-encoded cursor
- `sort`: Field to sort by (e.g., `abc12_created_date:desc`)

**Required Permission:** `data:read`

---

#### **ADVANCED QUERY**
```http
POST /api/v1/data/tenant_abc/abc12_customer_account/query

Request Body:
{
    "fields": ["abc12_email", "abc12_first_name", "abc12_status"],
    "filters": {
        "and": [
            {"field": "abc12_status", "op": "=", "value": "active"},
            {"field": "abc12_created_date", "op": ">=", "value": "2026-01-01"},
            {
                "or": [
                    {"field": "abc12_department", "op": "IN", "value": ["Sales", "Marketing"]},
                    {"field": "abc12_salary", "op": ">", "value": 100000}
                ]
            }
        ]
    },
    "sort": [
        {"field": "abc12_created_date", "direction": "DESC"}
    ],
    "pagination": {
        "method": "cursor",
        "limit": 100
    }
}

Response 200 OK:
{
    "status": "success",
    "data": [ ... ],
    "pagination": { ... }
}
```

**Supported Operators:**
- Equality: `=`, `!=`
- Comparison: `>`, `>=`, `<`, `<=`
- Pattern: `LIKE`, `ILIKE`, `NOT LIKE`
- Set: `IN`, `NOT IN`
- Null: `IS NULL`, `IS NOT NULL`
- Range: `BETWEEN`

**Required Permission:** `query:advanced`

---

#### **AGGREGATION**
```http
POST /api/v1/data/tenant_abc/abc12_customer_account/aggregate

Request Body:
{
    "metrics": [
        {"function": "count", "alias": "total_customers"},
        {"function": "sum", "field": "abc12_order_total", "alias": "total_revenue"},
        {"function": "avg", "field": "abc12_order_total", "alias": "avg_order"}
    ],
    "group_by": ["abc12_department", "abc12_status"],
    "filters": {
        "and": [
            {"field": "abc12_created_date", "op": ">=", "value": "2026-01-01"}
        ]
    }
}

Response 200 OK:
{
    "status": "success",
    "data": [
        {
            "abc12_department": "Sales",
            "abc12_status": "active",
            "total_customers": 1250,
            "total_revenue": 5400000.50,
            "avg_order": 4320.00
        }
    ]
}
```

**Required Permission:** `query:aggregation`

---

### 4.4 Bulk Operations (Asynchronous)

#### **BULK CREATE**
```http
POST /api/v1/data/tenant_abc/abc12_customer_account/bulk-create

Request Body:
{
    "records": [
        {"abc12_email": "user1@example.com", ...},
        {"abc12_email": "user2@example.com", ...},
        ...10,000 records
    ],
    "options": {
        "on_conflict": "skip",  // or "update" for upsert
        "conflict_fields": ["abc12_email"]
    }
}

Response 202 Accepted:
{
    "status": "accepted",
    "job": {
        "job_id": "job-uuid",
        status": "queued",
        "total_records": 10000,
        "status_url": "/api/v1/jobs/job-uuid",
        "created_at": "2026-03-10T12:00:00Z"
    }
}
```

**Required Permission:** `bulk:import`

---

#### **JOB STATUS**
```http
GET /api/v1/jobs/{job_id}

Response 200 OK (In Progress):
{
    "status": "processing",
    "job_id": "job-uuid",
    "operation": "bulk-create",
    "object": "abc12_customer_account",
    "total_records": 10000,
    "processed": 6500,
    "successful": 6450,
    "failed": 50,
    "progress_percent": 65,
    "errors_preview": [
        {"row": 123, "error": "Duplicate email"},
        {"row": 456, "error": "Invalid phone format"}
    ],
    "created_at": "2026-03-10T12:00:00Z",
    "estimated_completion": "2026-03-10T12:08:00Z"
}

Response 200 OK (Completed):
{
    "status": "completed",
    "total_records": 10000,
    "processed": 10000,
    "successful": 9950,
    "failed": 50,
    "progress_percent": 100,
    "results_url": "/api/v1/jobs/job-uuid/results",
    "errors_url": "/api/v1/jobs/job-uuid/errors",
    "created_at": "2026-03-10T12:00:00Z",
    "completed_at": "2026-03-10T12:07:30Z"
}
```

---

#### **BULK EXPORT**
```http
POST /api/v1/data/tenant_abc/abc12_customer_account/bulk-export

Request Body:
{
    "format": "csv",
    "fields": ["abc12_email", "abc12_first_name", "abc12_status"],
    "filters": {
        "and": [
            {"field": "abc12_status", "op": "=", "value": "active"}
        ]
    },
    "options": {
        "compression": "gzip",
        "split_every": 100000  // Files of 100K records each
    }
}

Response 202 Accepted:
{
    "status": "accepted",
    "job": {
        "job_id": "job-uuid",
        "status": "queued"
    }
}
```

**Required Permission:** `bulk:export:format:csv`

---

### 4.5 Error Response Format (RFC 7807)

```json
{
    "status": "error",
    "error": {
        "type": "https://api.appify.com/errors/validation-error",
        "title": "Validation Failed",
        "status": 400,
        "detail": "The email field is required",
        "instance": "/api/v1/data/tenant_abc/abc12_customer",
        "errors": [
            {
                "field": "abc12_email",
                "code": "required",
                "message": "Email is required"
            },
            {
                "field": "abc12_phone",
                "code": "invalid_format",
                "message": "Phone must be in E.164 format"
            }
        ]
    },
    "metadata": {
        "request_id": "uuid",
        "timestamp": "2026-03-10T10:30:00Z"
    }
}
```

**HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `202` - Accepted (async job)
- `204` - No Content
- `400` - Bad Request (validation error)
- `401` - Unauthorized (no/invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `409` - Conflict (duplicate unique field)
- `422` - Unprocessable (business rule violation)
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error
- `503` - Service Unavailable

---

## 5. Permission Enforcement

### 5.1 PermissionChecker Class

**Core Implementation:**
```python
class PermissionChecker:
    def __init__(self, permissions: List[str]):
        self.permissions = set(permissions)
        self._compiled_patterns = {}
        
        # Pre-compile wildcard patterns
        for perm in self.permissions:
            if '*' in perm:
                pattern = perm.replace('*', '.*')
                self._compiled_patterns[perm] = re.compile(f"^{pattern}$")
    
    def has(self, required: str) -> bool:
        """Check if user has permission"""
        # Exact match
        if required in self.permissions:
            return True
        
        # Wildcard patterns
        for perm, pattern in self._compiled_patterns.items():
            if pattern.match(required):
                return True
        
        # Hierarchical: data:read matched by data:*
        parts = required.split(':')
        for i in range(len(parts), 0, -1):
            wildcard = ':'.join(parts[:i]) + ':*'
            if wildcard in self.permissions:
                return True
        
        return False
    
    def get_scope(self, resource: str = 'data') -> str:
        """Get most permissive scope"""
        for scope in ['global', 'all', 'team', 'self']:
            if self.has(f"{resource}:read:scope:{scope}"):
                return scope
        return 'none'
    
    def get_modifier_value(self, permission: str, modifier: str) -> Optional[str]:
        """Extract modifier value (e.g., depth:2 from query:composite)"""
        pattern = f"{permission}:{modifier}:"
        for perm in self.permissions:
            if perm.startswith(pattern):
                return perm.split(':')[-1]
        return None
    
    def can_access_field(self, field_name: str, access_type: str = 'read') -> bool:
        """Check field-level permission"""
        if self.has(f"field:{access_type}:*"):
            return True
        return self.has(f"field:{access_type}:{field_name}")
    
    def is_field_masked(self, field_name: str) -> bool:
        """Check if field should be masked"""
        return self.has(f"field:mask:{field_name}")
    
    def is_field_hidden(self, field_name: str) -> bool:
        """Check if field should be hidden"""
        return self.has(f"field:hide:{field_name}")
```

### 5.2 SecureQueryBuilder Class

**Automatic Permission Enforcement:**
```python
class SecureQueryBuilder:
    def __init__(self, permissions, object_metadata, user_id, tenant_schema):
        self.permissions = permissions
        self.object_metadata = object_metadata
        self.user_id = user_id
        self.tenant_schema = tenant_schema
    
    def build_select(self, fields, filters, sort, limit, cursor):
        """Build SELECT with permission enforcement"""
        
        # 1. Filter fields by permissions
        allowed_fields = self.permissions.get_allowed_fields(fields, 'read')
        
        # 2. Build WHERE with scope enforcement
        where_clauses = ["is_deleted = false"]
        params = []
        
        scope = self.permissions.get_scope('data')
        if scope == 'self':
            where_clauses.append("created_by = %s")
            params.append(self.user_id)
        elif scope == 'team':
            where_clauses.append("created_by IN (...team members...)")
        
        # 3. Add user filters
        if filters:
            filter_sql, filter_params = self._build_filter_clause(filters)
            where_clauses.append(filter_sql)
            params.extend(filter_params)
        
        # 4. Build final SQL
        sql = f"""
            SELECT {', '.join(allowed_fields)}
            FROM {self.tenant_schema}.{self.table_name}
            WHERE {' AND '.join(where_clauses)}
            ORDER BY {order_by}
            LIMIT %s
        """
        params.append(limit)
        
        return sql, params
```

**Key Features:**
- ✅ **Automatic field filtering** based on permissions
- ✅ **Row-level security** via scope enforcement
- ✅ **SQL injection prevention** via parameterized queries
- ✅ **Operator validation** based on query permission level

---

## 6. Query & Filter System

### 6.1 Filter Specification

**Nested AND/OR Logic:**
```json
{
    "and": [
        {"field": "abc12_status", "op": "=", "value": "active"},
        {
            "or": [
                {"field": "abc12_department", "op": "IN", "value": ["Sales", "Marketing"]},
                {"field": "abc12_salary", "op": ">", "value": 100000}
            ]
        }
    ]
}
```

**Converted to SQL:**
```sql
WHERE abc12_status = 'active'
  AND (abc12_department IN ('Sales', 'Marketing') OR abc12_salary > 100000)
```

### 6.2 Pagination Strategies

**Cursor-Based (Recommended for Large Datasets):**

**Advantages:**
- ✅ Constant performance regardless of offset
- ✅ No duplicate/missing rows during concurrent writes
- ✅ Stateless (cursor contains all info)

**Cursor Format:**
```json
{
    "last_id": "uuid-100",
    "last_sort_value": "2026-03-09T10:30:00Z",
    "direction": "next"
}
```

**Base64 Encoded:** `eyJsYXN0X2lkIjoidXVpZC0xMDAiLC...`

**SQL Query:**
```sql
SELECT * FROM table
WHERE (sort_field, id) > ('2026-03-09T10:30:00Z', 'uuid-100')
ORDER BY sort_field, id
LIMIT 100
```

---

## 7. Bulk Operations

### 7.1 Asynchronous Job Architecture

```
Client Request → API → Job Queue (Redis) → Worker Pool → Database
                  ↓
            Job ID (202 Accepted)
                  
Client Polls → GET /jobs/{id} → Job Status/Results
```

### 7.2 Job Processing Strategy

**Chunking:**
- Large operation (10,000 records) → Split into chunks of 500
- Process each chunk in separate transaction
- Checkpoint progress after each chunk
- Resume from checkpoint on failure

**Transaction per Chunk:**
```python
for chunk in chunks_of_500(records):
    BEGIN TRANSACTION
    try:
        INSERT INTO table VALUES (...)  # 500 rows
        COMMIT
        update_progress(job_id, processed=500)
    except:
        ROLLBACK
        log_errors(job_id, chunk_errors)
```

**Benefits:**
- ✅ **Partial success**: 9,500 succeed even if 500 fail
- ✅ **Progress tracking**: Real-time progress updates
- ✅ **Resumable**: Can retry failed chunks
- ✅ **Memory efficient**: Small chunks don't overwhelm memory

### 7.3 Job Storage

```sql
CREATE TABLE sys_bulk_jobs (
    id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    object_id UUID NOT NULL,
    operation TEXT NOT NULL,  -- bulk-create, bulk-update, bulk-export
    status TEXT NOT NULL,  -- queued, processing, completed, failed
    total_records INTEGER,
    processed INTEGER DEFAULT 0,
    successful INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    input_file_url TEXT,
    result_file_url TEXT,
    error_file_url TEXT,
    created_by UUID NOT NULL,
    created_date TIMESTAMP DEFAULT now(),
    started_date TIMESTAMP,
    completed_date TIMESTAMP,
    expires_date TIMESTAMP,  -- TTL for cleanup
    
    CONSTRAINT valid_status CHECK (status IN ('queued', 'processing', 'completed', 'failed'))
);

CREATE INDEX idx_bulk_jobs_status ON sys_bulk_jobs(status) WHERE status IN ('queued', 'processing');
CREATE INDEX idx_bulk_jobs_tenant ON sys_bulk_jobs(tenant_id);
CREATE INDEX idx_bulk_jobs_created ON sys_bulk_jobs(created_by);
```

---

## 8. Caching Strategy

### 8.1 Cache Layers

**Multi-Level Cache:**

```
Request → L1 (App Memory) → L2 (Redis) → L3 (Database)
          ↓ Hit: 1ms        ↓ Hit: 5ms    ↓ Hit: 50ms
```

### 8.2 Redis Cache Structure

```python
# Permission cache (5-min TTL)
Key: perm:{object_id}:{role_id}
Value: {
    "permissions": ["data:read:scope:all", ...],
    "row_filter": "...",
    "expires_at": 1234567890
}
TTL: 300 seconds

# Object metadata cache (invalidate on deploy)
Key: obj:{object_id}
Value: {object metadata JSON}
TTL: None (manual invalidation)

# Single record cache (1-min TTL)
Key: rec:{table}:{id}:{version}
Value: {record data}
TTL: 60 seconds

# Query result cache (30-sec TTL)
Key: query:{hash(query_spec)}
Value: {
    "data": [...],
    "pagination": {...}
}
TTL: 30 seconds
```

### 8.3 Cache Invalidation

**Strategies:**

1. **Time-based (TTL)**: Automatic expiration
2. **Event-based**: Invalidate on write operations
3. **Version-based**: Increment version number on update

**Implementation:**
```python
# On record update
redis_client.delete(f"rec:{table}:{id}:*")
redis_client.publish('cache_invalidate', {
    'type': 'record',
    'table': table,
    'id': id
})

# On object deployment
redis_client.delete(f"obj:{object_id}")
redis_client.delete_pattern(f"query:{table}:*")
```

---

## 9. Security

### 9.1 SQL Injection Prevention

**Golden Rules:**

✅ **ALWAYS use parameterized queries:**
```python
cursor.execute(
    "SELECT * FROM table WHERE email = %s",
    (email,)
)
```

❌ **NEVER use string formatting:**
```python
# DANGEROUS - DO NOT DO THIS
cursor.execute(f"SELECT * FROM table WHERE email = '{email}'")
```

**Table/Column Name Validation:**
```python
def validate_field(field: str, allowed_fields: List[str]) -> bool:
    """Whitelist validation against object metadata"""
    return field in allowed_fields

def get_table_name(object_id: UUID) -> str:
    """Get table name from metadata only"""
    metadata = get_object_metadata(object_id)
    if not metadata:
        raise ValueError("Invalid object ID")
    return metadata['api_name']
```

### 9.2 Permission Defense in Depth

**Multiple Layers:**

1. **API Gateway**: JWT validation
2. **Service Layer**: Permission check before query builder
3. **Query Builder**: Inject scope filters into SQL
4. **Database**: Row-level security policies (optional)

**Fail-Closed Pattern:**
```python
def check_permission(user, permission):
    try:
        perms = load_permissions(user)
        return perms.has(permission)
    except Exception as e:
        logger.error(f"Permission check failed: {e}")
        return False  # Deny on error
```

### 9.3 Rate Limiting

**Token Bucket Algorithm:**
```python
class RateLimiter:
    def check(self, key: str, max_requests: int, window_sec: int) -> bool:
        now = time.time()
        window_key = f"rate:{key}:{int(now // window_sec)}"
        
        count = redis.incr(window_key)
        if count == 1:
            redis.expire(window_key, window_sec * 2)
        
        return count <= max_requests

# Usage
if not limiter.check(f"user:{user_id}:read", 100, 60):
    raise HTTPException(429, "Rate limit exceeded")
```

**Permission-Based Limits:**
```python
# Extract from permissions
read_limit = permissions.get_modifier_value("ratelimit", "read") or "100"
write_limit = permissions.get_modifier_value("ratelimit", "write") or "50"
```

### 9.4 Audit Trail

**Immutable Append-Only Log:**
```sql
CREATE TABLE sys_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    record_id UUID NOT NULL,
    operation TEXT NOT NULL,  -- CREATE, UPDATE, DELETE, RESTORE
    user_id UUID NOT NULL,
    changes JSONB,  -- {"before": {...}, "after": {...}}
    request_id UUID NOT NULL,
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT now()
) PARTITION BY RANGE (timestamp);

-- Monthly partitions for performance
CREATE TABLE sys_audit_log_202603 PARTITION OF sys_audit_log
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

---

## 10. Performance & Scalability

### 10.1 Database Optimizations

**Indexing Strategy (Auto-created on deployment):**

1. **Primary key**: `id` (UUID)
2. **System fields**:
   - `created_date DESC` - Recent records queries
   - `modified_date DESC` - Recently changed queries
   - `is_deleted` WHERE `is_deleted = true` - Restore queries (partial)
3. **Unique fields**: Any field marked `unique`
4. **Reference fields**: Foreign keys (for JOINs)
5. **User-defined**: From object metadata `indexes` JSONB field

**Read Replicas:**
```
Writes → Primary DB
Reads → Round-robin across 3 read replicas
Strong consistency reads (when needed) → Primary DB
```

**Connection Pooling (PgBouncer):**
```
100 Application Connections
    ↓
PgBouncer (transaction mode)
    ↓
20 Actual Database Connections
```

### 10.2 Horizontal Scaling

**Stateless API Servers:**
```
Load Balancer (ALB)
  ├─ API Server 1 (auto-scale 1-20 instances)
  ├─ API Server 2
  └─ API Server N
       ↓
  Connection Pool (PgBouncer)
       ↓
  PostgreSQL (Primary + Replicas)
```

**Auto-Scaling Triggers:**
- CPU > 70% → Scale up
- Request latency p99 > 500ms → Scale up
- CPU < 30% for 10 min → Scale down

### 10.3 Query Performance

**EXPLAIN Cost Estimation:**
```python
# Before executing user query
EXPLAIN (FORMAT JSON) SELECT ...
→ estimated_cost = 50,000
→ If cost > threshold (10,000): REJECT
→ Suggest: "Add index on abc12_department"
```

**Query Timeout:**
```sql
SET statement_timeout = '30s';
SELECT ...
```

**Result Limits:**
- Single query: Max 10,000 rows (use pagination)
- Bulk export: No limit (async job)

### 10.4 Future: Database Sharding

**When to shard:** Single tenant > 100M records

**Shard key:** `tenant_id` (each tenant on separate database)

**Benefits:**
- ✅ Tenant isolation
- ✅ Smaller indexes = faster queries
- ✅ Data residency compliance (EU data stays in EU)

**Trade-off:**
- ❌ Cross-tenant queries impossible (acceptable - different customers)

---

## 11. Implementation Plan

### 11.1 Phase 1: Foundation (Months 1-2)

**Deliverables:**
- [ ] `sys_object_permissions` table created
- [ ] `PermissionChecker` class implemented
- [ ] `SecureQueryBuilder` class implemented
- [ ] Permission resolution layer (cache + DB)
- [ ] Unit tests (90% coverage)
- [ ] Documentation

**Team:** 2 backend engineers

---

### 11.2 Phase 2: Core Data API (Months 3-4)

**Deliverables:**
- [ ] Single-record CRUD endpoints (Create, Read, Update, Delete)
- [ ] List/Query endpoints with pagination
- [ ] Field-level permission enforcement
- [ ] Field masking/hiding logic
- [ ] Error handling (RFC 7807 format)
- [ ] Integration tests
- [ ] API documentation (OpenAPI/Swagger)

**Team:** 2 backend engineers + 1 QA

---

### 11.3 Phase 3: Bulk Operations (Months 5-6)

**Deliverables:**
- [ ] Redis job queue setup
- [ ] Worker pool implementation
- [ ] Bulk import/export jobs
- [ ] Job management endpoints (status, results, errors)
- [ ] Chunked processing with checkpoints
- [ ] Load testing (1M+ records)
- [ ] Performance optimization

**Team:** 2 backend engineers + 1 DevOps

---

### 11.4 Phase 4: Advanced Features (Months 7-8)

**Deliverables:**
- [ ] Composite queries (nested/chained)
- [ ] Aggregation API (COUNT, SUM, AVG, GROUP BY)
- [ ] Webhook triggers
- [ ] Audit trail enhancements
- [ ] Query cost estimation
- [ ] Performance monitoring (Prometheus/Grafana)

**Team:** 2 backend engineers + 1 DevOps

---

### 11.5 Phase 5: Production Launch (Month 9)

**Deliverables:**
- [ ] Security audit (penetration testing)
- [ ] Load testing (10M+ records, 1000 req/sec)
- [ ] Complete documentation
- [ ] Developer SDK (Python, JavaScript)
- [ ] Beta rollout (select customers)
- [ ] Production deployment
- [ ] Post-launch monitoring

**Team:** Full team + Security consultants

---

## 12. Appendices

### Appendix A: Permission Examples

**Sales Representative:**
```json
{
    "permissions": [
        "data:read:scope:team",
        "data:create",
        "data:update:scope:self",
        "query:basic",
        "bulk:export:format:csv",
        "field:read:*",
        "field:write:abc12_status",
        "field:mask:abc12_salary",
        "field:hide:abc12_ssn"
    ]
}
```

**Data Analyst:**
```json
{
    "permissions": [
        "data:read:scope:all",
        "query:advanced",
        "query:aggregation",
        "bulk:export:format:*",
        "field:read:*",
        "field:hide:abc12_ssn"
    ]
}
```

**Administrator:**
```json
{
    "permissions": [
        "data:*",
        "bulk:*",
        "query:*",
        "schema:*",
        "admin:*",
        "field:*"
    ]
}
```

---

### Appendix B: Sample Workflows

**Workflow 1: User Creates Record**
```
1. POST /api/v1/data/tenant_abc/abc12_customer
2. API Gateway validates JWT
3. Permission check: has("data:create") → Yes
4. Filter writable fields
5. Build INSERT with created_by = user_id
6. Execute query
7. Return 201 Created
8. Async: Write audit log
```

**Workflow 2: Bulk Import 10,000 Records**
```
1. POST /bulk-create with 10,000 records
2. Permission check: has("bulk:import") + limit check
3. Create job record, enqueue to Redis
4. Return 202 Accepted with job_id
5. Worker: Process in 20 chunks of 500
6. Each chunk: BEGIN → INSERT → COMMIT → Update progress
7. Generate results CSV
8. Client polls: GET /jobs/{id} → 100% complete
9. Client downloads results
```

---

### Appendix C: Glossary

| Term | Definition |
|------|------------|
| **IAM** | Identity and Access Management |
| **RBAC** | Role-Based Access Control |
| **Scope** | Level of data access (self, team, all, global) |
| **Field Masking** | Showing partial data (e.g., ****1234) |
| **Soft Delete** | Marking record as deleted without physical removal |
| **Cursor Pagination** | Stateless pagination using last record as reference point |
| **Bulk Operation** | Processing large number of records asynchronously |
| **Composite Query** | Nested query where one query feeds into another |
| **Row-Level Security** | Filtering data based on user context in WHERE clause |

---

### Appendix D: Key Decisions

| Decision | Rationale |
|----------|-----------|
| **IAM-style permissions** | Industry-standard, extensible, self-documenting |
| **Cursor pagination** | Constant performance at scale, no offset issues |
| **Async bulk operations** | Prevents timeouts, allows partial success, resumable |
| **Redis for cache/queue** | Simple, reliable, supports pub/sub for invalidation |
| **PostgreSQL** | JSONB support, strong consistency, mature tooling |
| **PgBouncer pooling** | Reduces DB connections, improves resource usage |
| **Fail-closed permissions** | Security-first: deny on error/uncertainty |

---

## Document Control

**Version History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-10 | System Architecture | Initial design document |

**Review & Approval:**

- [ ] Technical Lead Review
- [ ] Security Team Review
- [ ] Architecture Council Approval
- [ ] Product Owner Sign-off

**Distribution:**

- Engineering Team
- Product Management
- Security Team
- DevOps Team

---

**END OF DOCUMENT**
