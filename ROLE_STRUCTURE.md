# Phase 0: Role Structure Reference

**Date:** March 10, 2026

---

## System Roles Overview

### Core Database (public schema)
Location: `unshackle_core` database, `public` schema

| Role Name | Type | Description | Script |
|-----------|------|-------------|--------|
| `appify_admin` | System | Full platform admin - can manage tenant_registry, system config | [phase0-core-bootstrap.sql](sql/phase0-core-bootstrap.sql) |
| `appify_user` | System | Read-only platform user - monitoring, basic operations | [phase0-core-bootstrap.sql](sql/phase0-core-bootstrap.sql) |

**Permissions:**
- `appify_admin`: `["data:*", "bulk:*", "query:*", "schema:*", "admin:*", "field:*"]`
- `appify_user`: `["data:read:scope:all", "query:basic", "field:read:*"]`

**When to assign:**
- Assign when creating Keycloak user who needs access to core database
- Typically: Appify internal staff, platform administrators

---

### Tenant Schemas (tenant_*)
Location: `unshackle_core` database, `tenant_{customer_id}` schema

| Role Name | Type | Description | Script |
|-----------|------|-------------|--------|
| `customer_admin` | System | Full customer admin - can manage all data, objects, users | [phase0-tenant-bootstrap.sql](sql/phase0-tenant-bootstrap.sql) |
| `customer_user` | System | Standard user - team-level access with restrictions | [phase0-tenant-bootstrap.sql](sql/phase0-tenant-bootstrap.sql) |
| *(custom)* | Custom | Customer-defined roles (sales_manager, analyst, etc.) | Defined by customer |

**Permissions:**
- `customer_admin`: `["data:*", "bulk:*", "query:*", "schema:modify", "field:*"]`
- `customer_user`: `["data:read:scope:team", "data:create", "data:update:scope:self", "query:advanced", ...]` + row-level filter

**When to assign:**
- Assign when creating Keycloak user who belongs to this customer
- Use Keycloak Group to determine which tenant schema
- Assign role based on Keycloak role assignment

---

## Keycloak → Database Sync Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    KEYCLOAK                                  │
├─────────────────────────────────────────────────────────────┤
│ 1. Create User                                               │
│ 2. Assign to Group (determines customer/tenant)             │
│ 3. Assign Keycloak Roles:                                   │
│    - For core access: appify-admin or appify-user          │
│    - For tenant access: customer-admin or customer-user    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    SYNC SERVICE                              │
│  (Webhook or API call)                                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE                                  │
├─────────────────────────────────────────────────────────────┤
│ 1. Determine schema based on Group:                         │
│    - No group or "Appify" group → public schema             │
│    - Customer group → tenant_{customer_id} schema           │
│                                                               │
│ 2. INSERT into sys_users                                    │
│    (user_id = Keycloak UUID)                                │
│                                                               │
│ 3. Map Keycloak role to sys_roles:                          │
│    - appify-admin → appify_admin                            │
│    - customer-admin → customer_admin                        │
│    etc.                                                       │
│                                                               │
│ 4. INSERT into sys_user_roles                               │
│    (links user to role)                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Bootstrap Scripts

### 1. Core Database Bootstrap
**File:** `sql/phase0-core-bootstrap.sql`

**Run on:** `public` schema (one-time setup)

**Creates:**
- `appify_admin` role
- `appify_user` role
- Permissions for `tenant_registry` object
- Sample platform admin user (optional)

**Command:**
```bash
psql -h localhost -U postgres -d unshackle_core << 'EOF'
SET search_path TO public;
\i sql/phase0-core-bootstrap.sql
EOF
```

---

### 2. Tenant Bootstrap
**File:** `sql/phase0-tenant-bootstrap.sql`

**Run on:** Each `tenant_*` schema

**Creates:**
- `customer_admin` role
- `customer_user` role
- Permissions for ALL objects in tenant (dynamic)
- Sample customer users (optional)
- Example custom roles (sales_manager, sales_rep)

**Command:**
```bash
psql -h localhost -U postgres -d unshackle_core << 'EOF'
SET search_path TO tenant_abc123;  -- Replace with actual tenant
\i sql/phase0-tenant-bootstrap.sql
EOF
```

---

## Custom Roles (Customer-Defined)

Customers can create their own roles beyond the 2 system roles.

**Example:**
```sql
-- In tenant schema
INSERT INTO sys_roles (role_name, description, is_system_role, created_by, modified_by)
VALUES (
    'sales_director',
    'Sales director with full sales data access',
    false,  -- NOT a system role
    '{admin_user_id}',
    '{admin_user_id}'
);

-- Grant permissions
INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT 
    r.id,
    o.id,
    '["data:read:scope:all", "data:update:scope:team", "query:aggregation"]'::jsonb,
    '{admin_user_id}',
    '{admin_user_id}'
FROM sys_roles r, sys_object_metadata o
WHERE r.role_name = 'sales_director'
  AND o.api_name = 'abc12_opportunity';
```

---

## Permission Examples

### appify_admin (Core)
```json
{
  "role": "appify_admin",
  "object": "tenant_registry",
  "permissions": [
    "data:*",              // All CRUD
    "bulk:*",              // All bulk ops
    "query:*",             // All query types
    "schema:*",            // Schema management
    "admin:*",             // Admin operations
    "field:*"              // All fields
  ]
}
```

### customer_admin (Tenant)
```json
{
  "role": "customer_admin",
  "object": "abc12_customer_account",
  "permissions": [
    "data:*",              // All CRUD
    "bulk:*",              // All bulk ops
    "query:*",             // All query types
    "schema:modify",       // Can modify metadata
    "field:*"              // All fields
  ]
}
```

### customer_user (Tenant)
```json
{
  "role": "customer_user",
  "object": "abc12_customer_account",
  "permissions": [
    "data:read:scope:team",        // Read team records
    "data:create",                  // Create new
    "data:update:scope:self",       // Update own only
    "data:delete:scope:self",       // Delete own only
    "query:basic",                  // Basic queries
    "query:advanced",               // Advanced filters
    "bulk:export:format:csv",       // CSV export only
    "field:read:*"                  // Read all fields
  ],
  "row_filter": "created_by = $user_id OR assigned_to = $user_id"
}
```

---

## Verification Queries

### Check Roles in Schema
```sql
SELECT 
    role_name, 
    description, 
    is_system_role,
    is_active
FROM sys_roles
ORDER BY is_system_role DESC, role_name;
```

### Check User-Role Assignments
```sql
SELECT 
    u.username,
    u.email,
    r.role_name,
    ur.assigned_date
FROM sys_user_roles ur
JOIN sys_users u ON ur.user_id = u.id
JOIN sys_roles r ON ur.role_id = r.id
WHERE ur.is_active = true
ORDER BY u.username;
```

### Check Effective Permissions for User
```sql
SELECT 
    u.username,
    r.role_name,
    o.api_name as object_name,
    op.permissions
FROM sys_users u
JOIN sys_user_roles ur ON u.id = ur.user_id AND ur.is_active = true
JOIN sys_roles r ON ur.role_id = r.id AND r.is_active = true
JOIN sys_object_permissions op ON r.id = op.role_id AND op.is_active = true
JOIN sys_object_metadata o ON op.object_id = o.id
WHERE u.email = 'user@customer.com'  -- Replace with actual user
ORDER BY r.role_name, o.api_name;
```

---

## Files Reference

| File | Purpose | Location |
|------|---------|----------|
| [tenant-base-schema.sql](sql/tenant-base-schema.sql) | Modified - includes 3 new tables | Modified (Phase 0) |
| [phase0-migration-existing-schemas.sql](sql/phase0-migration-existing-schemas.sql) | Migrate existing schemas | New (Phase 0) |
| [phase0-core-bootstrap.sql](sql/phase0-core-bootstrap.sql) | Bootstrap core roles | New (Phase 0) |
| [phase0-tenant-bootstrap.sql](sql/phase0-tenant-bootstrap.sql) | Bootstrap tenant roles | New (Phase 0) |
| [PHASE0_SUMMARY.md](PHASE0_SUMMARY.md) | Complete Phase 0 documentation | New (Phase 0) |
