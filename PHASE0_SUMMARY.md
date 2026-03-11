# Phase 0: Permission Infrastructure Foundation

**Status:** Ready for Testing  
**Date:** March 10, 2026

---

## Overview

Phase 0 establishes the database foundation for the IAM-style permission system. This includes creating tables to store users, roles, role assignments, and object-level permissions.

These tables will be created in **ALL schemas** (both `public` for core database and all `tenant_*` schemas) to enable consistent permission management across the entire system.

---

## Architecture

### Database Structure

```
unshackle_core (database)
├── public schema (CORE DATABASE)
│   ├── tenant_registry             # Existing - customer tracking
│   ├── sys_object_metadata         # Existing - core table metadata
│   ├── sys_users                   # Existing - user records
│   ├── sys_roles                   # NEW - role definitions
│   ├── sys_user_roles              # NEW - user-to-role mapping
│   └── sys_object_permissions      # NEW - IAM-style permissions
│
├── tenant_abc123 schema (TENANT)
│   ├── sys_object_metadata         # Existing - tenant object metadata
│   ├── sys_users                   # Existing - tenant user records
│   ├── sys_roles                   # NEW - tenant role definitions
│   ├── sys_user_roles              # NEW - user-to-role mapping
│   ├── sys_object_permissions      # NEW - IAM-style permissions
│   └── abc123_customer_account     # User-created tables
```

### User & Permission Flow

```
KEYCLOAK:
User → Group (determines customer) → Roles

DATABASE:
sys_users → sys_user_roles → sys_roles → sys_object_permissions → sys_object_metadata
```

**Flow:**
1. User created in Keycloak and assigned to Group (customer)
2. User synced to database → Insert into `sys_users` (in appropriate schema)
3. User assigned roles in Keycloak
4. Roles synced to database → Link via `sys_user_roles`
5. Roles have permissions → `sys_object_permissions` defines what each role can do
6. Permission check → Merge all role permissions for a user

---

## Tables Created

### 1. `sys_users` ✅ (Already Exists)
**Purpose:** Maps Keycloak users to database context

**Key Fields:**
- `user_id` - Keycloak user UUID (unique)
- `email`, `username` - Identity
- `is_active` - Enable/disable user

**Note:** This table already existed in tenant-base-schema.sql

---

### 2. `sys_roles` 🆕 (NEW - Phase 0)
**Purpose:** Defines roles available in this schema/database

**Key Fields:**
- `id` - Primary key
- `keycloak_role_id` - Optional link to Keycloak role
- `role_name` - Unique role name (e.g., 'admin', 'sales_rep')
- `description` - Human-readable description
- `is_system_role` - True for built-in roles, false for custom
- `is_active` - Enable/disable role

**Examples:**
- `admin` - Full access
- `developer` - Can create/modify objects
- `analyst` - Read-only with advanced queries
- `sales_rep` - Team-level data access
- `viewer` - Basic read-only

---

### 3. `sys_user_roles` 🆕 (NEW - Phase 0)
**Purpose:** Many-to-many mapping between users and roles

**Key Fields:**
- `user_id` - References `sys_users(id)`
- `role_id` - References `sys_roles(id)`
- `assigned_by` - Who assigned this role
- `assigned_date` - When assigned
- `expires_date` - Optional expiration for temporary assignments
- `is_active` - Enable/disable assignment

**Unique Constraint:** `(user_id, role_id)` - One assignment per user-role pair

---

### 4. `sys_object_permissions` 🆕 (NEW - Phase 0)
**Purpose:** IAM-style permissions for each role on each object

**Key Fields:**
- `role_id` - References `sys_roles(id)`
- `object_id` - References `sys_object_metadata(id)`
- `permissions` - JSONB array of permission strings
- `row_filter` - Optional SQL WHERE clause for row-level security
- `field_permissions` - Optional JSONB for field-level access control
- `is_active` - Enable/disable permissions

**Unique Constraint:** `(role_id, object_id)` - One permission set per role-object pair

**Permission Examples:**
```json
{
  "permissions": [
    "data:read:scope:all",
    "data:create",
    "query:advanced",
    "bulk:export:format:csv",
    "field:read:*"
  ],
  "row_filter": "created_by = $user_id OR department = $user_department",
  "field_permissions": {
    "salary": {"access": "mask"},
    "ssn": {"access": "hide"}
  }
}
```

---

## Files Created/Modified

### Modified Files

#### 1. `appify-om/sql/tenant-base-schema.sql` ✏️
**Changes:**
- Added `sys_roles` table definition (lines ~156-185)
- Added `sys_user_roles` table definition (lines ~186-205)
- Added `sys_object_permissions` table definition (lines ~206-240)

**Impact:**
- All **NEW** tenant schemas will automatically include these tables
- Existing tenant schemas need manual migration

---

### New Files Created

#### 2. `appify-om/sql/phase0-migration-existing-schemas.sql` 🆕
**Purpose:** Manual migration script for existing schemas

**Usage:**
```sql
-- Option 1: Manual per-schema
SET search_path TO tenant_abc123;
-- Run CREATE TABLE statements

-- Option 2: Verify
SELECT table_name, column_count 
FROM information_schema.tables 
WHERE table_name IN ('sys_roles', 'sys_user_roles', 'sys_object_permissions');
```

#### 3. `appify-om/sql/phase0-core-bootstrap.sql` 🆕
**Purpose:** Bootstrap system roles for CORE database (public schema)

**Contains:**
- **2 System Roles:**
  - `appify_admin` - Full platform admin access
  - `appify_user` - Read-only platform user
- Object metadata for `tenant_registry`
- Permissions for both roles
- Sample admin user
- Verification queries

**Usage:**
```sql
-- Connect to unshackle_core database
SET search_path TO public;
\i phase0-core-bootstrap.sql
```

#### 4. `appify-om/sql/phase0-tenant-bootstrap.sql` 🆕
**Purpose:** Bootstrap system roles for TENANT schemas

**Contains:**
- **2 System Roles:**
  - `customer_admin` - Full customer data access
  - `customer_user` - Team-level restricted access
- **Custom Role Examples:**
  - `sales_manager`, `sales_rep` (customer-defined)
- Permissions for all objects in tenant
- Sample users and role assignments
- Verification queries

**Usage:**
```sql
-- Connect to unshackle_core database
SET search_path TO tenant_abc123;  -- Replace with actual tenant
\i phase0-tenant-bootstrap.sql
```

#### 5. `appify-om/sql/phase0-sample-data.sql` 🆕 *(DEPRECATED - Use scripts 3 & 4 above)*
**Purpose:** Old generic sample data (replaced by core-bootstrap and tenant-bootstrap)

---

## Testing Plan

### Step 1: Test Existing Schema (Manual Migration)

1. **Connect to database:**
   ```bash
   psql -h localhost -U your_user -d unshackle_core
   ```

2. **Run migration for one test tenant:**
   ```sql
   SET search_path TO tenant_abc123;
   \i sql/phase0-migration-existing-schemas.sql
   ```

3. **Verify tables created:**
   ```sql
   SELECT table_name FROM information_schema.tables 
   WHERE table_schema = current_schema() 
   AND table_name LIKE 'sys_%'
   ORDER BY table_name;
   ```

4. **Load sample data:**
   ```sql
   -- For tenant schema
   \i sql/phase0-tenant-bootstrap.sql
   
   -- Alternatively, for core schema
   SET search_path TO public;
   \i sql/phase0-core-bootstrap.sql
   ```

5. **Test queries:**
   ```sql
   -- Check roles (expect: customer_admin, customer_user for tenant)
   SELECT * FROM sys_roles;
   
   -- Check permissions
   SELECT r.role_name, o.api_name, op.permissions
   FROM sys_object_permissions op
   JOIN sys_roles r ON op.role_id = r.id
   JOIN sys_object_metadata o ON op.object_id = o.id;
   ```

### Step 2: Test New Tenant Provisioning

1. **Create a new customer** using your existing provisioning flow

2. **Verify new tenant schema** has all tables:
   ```sql
   SET search_path TO tenant_{new_id};
   
   SELECT table_name 
   FROM information_schema.tables 
   WHERE table_schema = current_schema() 
   AND table_name IN ('sys_users', 'sys_roles', 'sys_user_roles', 'sys_object_permissions');
   ```

3. **Expected result:** All 4 tables should exist in the new tenant schema

### Step 3: Verify Foreign Keys Work

```sql
-- Create a role
INSERT INTO sys_roles (role_name, description, is_system_role, created_by, modified_by)
VALUES ('test_role', 'Test role', false, '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000');

-- Try to create permission for non-existent object (should fail)
INSERT INTO sys_object_permissions (role_id, object_id, created_by, modified_by)
SELECT id, '99999999-9999-9999-9999-999999999999', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'
FROM sys_roles WHERE role_name = 'test_role';
-- Expected: ERROR - foreign key violation

-- Create permission for existing object (should succeed)
INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT r.id, o.id, '["data:read"]'::jsonb, '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'
FROM sys_roles r, sys_object_metadata o
WHERE r.role_name = 'test_role' 
LIMIT 1;
-- Expected: SUCCESS
```

---

## Next Steps After Phase 0

Once Phase 0 is tested and working:

### Phase 1: Permission Logic Implementation
- Create `PermissionChecker` Python class
- Create `SecureQueryBuilder` Python class
- Implement permission resolution (merge roles)
- Add Redis caching for permissions
- Unit tests

### Phase 2: Data API Implementation
- Single-record CRUD endpoints
- Query/List endpoints with pagination
- Permission enforcement in API layer
- Integration tests

### Phase 3: Bulk Operations
- Redis job queue
- Worker pool
- Bulk import/export
- Job management API

---

## Rollback Plan

If issues are found during testing:

```sql
-- Drop tables in reverse order (to respect foreign keys)
DROP TABLE IF EXISTS sys_object_permissions;
DROP TABLE IF EXISTS sys_user_roles;
DROP TABLE IF EXISTS sys_roles;
-- Note: Keep sys_users as it existed before
```

To rollback from tenant-base-schema.sql:
1. Revert commit or manually remove the TABLE definitions
2. New tenants will not have the tables
3. Existing migrated tenants will need manual cleanup

---

## Success Criteria

Phase 0 is complete when:

- ✅ All 4 tables exist in tenant-base-schema.sql
- ✅ Migration script tested on at least one existing tenant schema
- ✅ Sample data loads successfully
- ✅ New tenant provisioning creates all 4 tables automatically
- ✅ Foreign key constraints work correctly
- ✅ Verification queries return expected results

---

## Summary

**What Changed:**
- Added 3 new tables to tenant-base-schema.sql (sys_roles, sys_user_roles, sys_object_permissions)
- Created migration script for existing schemas
- Created sample data for testing

**What's Next:**
- User tests migration on existing schema
- User tests new tenant provisioning
- If successful → Proceed to Phase 1 (Python implementation)

**Files to Review:**
1. `appify-om/sql/tenant-base-schema.sql` (modified)
2. `appify-om/sql/phase0-migration-existing-schemas.sql` (new)
3. `appify-om/sql/phase0-sample-data.sql` (new)
