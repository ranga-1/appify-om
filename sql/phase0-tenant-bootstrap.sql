-- ============================================================================
-- PHASE 0: Tenant Schema Bootstrap - System Roles & Permissions
-- ============================================================================
-- Database: unshackle_core
-- Schema: tenant_{customer_id}
-- Purpose: Create system roles for tenant-specific data access
--
-- EXECUTION INSTRUCTIONS:
-- 1. Connect to unshackle_core database
-- 2. Run: SET search_path TO tenant_{customer_id};  -- Replace with actual tenant schema
-- 3. Run this script
-- 4. Repeat for each tenant schema as needed
--
-- NOTE: For NEW tenants, you may want to run this automatically during provisioning
-- ============================================================================

-- IMPORTANT: Set your tenant schema
-- SET search_path TO tenant_abc123;  -- Replace abc123 with actual tenant ID

-- System user UUID for created_by/modified_by
-- 00000000-0000-0000-0000-000000000000 = SYSTEM

-- ============================================================================
-- SYSTEM ROLES (Tenant-specific)
-- ============================================================================

-- customer_admin: Full administrative access to this customer's data
INSERT INTO sys_roles (role_name, description, is_system_role, is_active, created_by, modified_by)
VALUES 
    ('customer_admin', 
     'Customer administrator - full access to all tenant data, objects, and configurations within this tenant schema', 
     true, 
     true, 
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000'),
    
    ('customer_user', 
     'Customer user - standard access to tenant data with scope restrictions based on ownership and team membership', 
     true, 
     true,
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000')
ON CONFLICT (role_name) DO NOTHING;


-- ============================================================================
-- PERMISSIONS: customer_admin Role
-- ============================================================================
-- Full access to ALL objects in this tenant schema
-- This will apply to any object created via sys_object_metadata

-- Note: Since we don't know which objects exist yet, this query may return 0 rows initially
-- As objects are deployed, re-run permission grants or create them via API

INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    jsonb_build_array(
        'data:*',              -- All data operations (create, read, update, delete)
        'bulk:*',              -- All bulk operations
        'query:*',             -- All query types (basic, advanced, aggregation, composite)
        'schema:modify',       -- Can modify object metadata
        'field:*'              -- All field access
    ) as permissions,
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'customer_admin'
  AND o.status = 'created'  -- Only deployed objects
ON CONFLICT (role_id, object_id) DO UPDATE
SET permissions = EXCLUDED.permissions,
    modified_date = now();


-- ============================================================================
-- PERMISSIONS: customer_user Role
-- ============================================================================
-- Team-level access with restrictions

INSERT INTO sys_object_permissions (role_id, object_id, permissions, row_filter, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    jsonb_build_array(
        'data:read:scope:team',        -- Read team records
        'data:create',                  -- Create new records
        'data:update:scope:self',       -- Update own records only
        'data:delete:scope:self',       -- Delete own records only
        'query:basic',                  -- Basic queries only
        'query:advanced',               -- Allow advanced filters
        'bulk:export:format:csv',       -- Export CSV only
        'field:read:*'                  -- Read all fields
    ) as permissions,
    'created_by = $user_id OR assigned_to = $user_id' as row_filter,  -- Row-level security
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'customer_user'
  AND o.status = 'created'  -- Only deployed objects
ON CONFLICT (role_id, object_id) DO UPDATE
SET permissions = EXCLUDED.permissions,
    row_filter = EXCLUDED.row_filter,
    modified_date = now();


-- ============================================================================
-- SAMPLE USERS (Optional - for testing in this tenant)
-- ============================================================================
-- Replace UUIDs and email with actual Keycloak user data

INSERT INTO sys_users (user_id, email, username, first_name, last_name, full_name, is_active, created_by, modified_by)
VALUES 
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 
     'admin@customer.com', 
     'customer_admin_user', 
     'Customer', 
     'Admin', 
     'Customer Admin', 
     true,
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000'),
     
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 
     'user@customer.com', 
     'customer_regular_user', 
     'Regular', 
     'User', 
     'Regular User', 
     true,
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000')
ON CONFLICT (user_id) DO NOTHING;

-- Assign customer_admin role
INSERT INTO sys_user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id as user_id,
    r.id as role_id,
    '00000000-0000-0000-0000-000000000000' as assigned_by
FROM sys_users u
CROSS JOIN sys_roles r
WHERE u.username = 'customer_admin_user' 
  AND r.role_name = 'customer_admin'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Assign customer_user role
INSERT INTO sys_user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id as user_id,
    r.id as role_id,
    '00000000-0000-0000-0000-000000000000' as assigned_by
FROM sys_users u
CROSS JOIN sys_roles r
WHERE u.username = 'customer_regular_user' 
  AND r.role_name = 'customer_user'
ON CONFLICT (user_id, role_id) DO NOTHING;


-- ============================================================================
-- CUSTOM ROLES EXAMPLE (Customer-specific)
-- ============================================================================
-- Customers can define their own roles beyond the 2 system roles
-- Example: A sales-specific role

INSERT INTO sys_roles (role_name, description, is_system_role, is_active, created_by, modified_by)
VALUES 
    ('sales_manager', 
     'Sales manager - can manage all sales-related records and view team performance', 
     false,  -- NOT a system role, customer-defined
     true,
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000'),
     
    ('sales_rep', 
     'Sales representative - can manage own leads and opportunities', 
     false,  -- NOT a system role, customer-defined
     true,
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000')
ON CONFLICT (role_name) DO NOTHING;

-- Example: Permissions for sales_manager on specific object
-- NOTE: This assumes an object called 'opportunity' exists
/*
INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    jsonb_build_array(
        'data:read:scope:all',
        'data:create',
        'data:update:scope:team',
        'data:delete:scope:team',
        'query:advanced',
        'query:aggregation',
        'bulk:export:format:*',
        'field:read:*',
        'field:write:*'
    ) as permissions,
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'sales_manager'
  AND o.api_name = 'abc12_opportunity'
ON CONFLICT (role_id, object_id) DO NOTHING;
*/


-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Check current schema
SELECT current_schema();

-- Check roles created
SELECT 
    role_name, 
    description, 
    is_system_role,
    is_active,
    created_date
FROM sys_roles
ORDER BY is_system_role DESC, role_name;

-- Check objects in this tenant
SELECT 
    api_name,
    label,
    status,
    table_created_date
FROM sys_object_metadata
ORDER BY api_name;

-- Check permissions
SELECT 
    r.role_name,
    r.is_system_role,
    o.api_name as object_name,
    op.permissions,
    op.row_filter,
    op.is_active
FROM sys_object_permissions op
JOIN sys_roles r ON op.role_id = r.id
JOIN sys_object_metadata o ON op.object_id = o.id
ORDER BY r.is_system_role DESC, r.role_name, o.api_name;

-- Check user-role assignments
SELECT 
    u.username,
    u.email,
    r.role_name,
    r.is_system_role,
    ur.assigned_date,
    ur.is_active
FROM sys_user_roles ur
JOIN sys_users u ON ur.user_id = u.id
JOIN sys_roles r ON ur.role_id = r.id
ORDER BY u.username, r.role_name;

-- Full permission resolution for a user
SELECT 
    u.username,
    u.email,
    r.role_name,
    o.api_name as object_name,
    op.permissions,
    op.row_filter
FROM sys_users u
JOIN sys_user_roles ur ON u.id = ur.user_id AND ur.is_active = true
JOIN sys_roles r ON ur.role_id = r.id AND r.is_active = true
LEFT JOIN sys_object_permissions op ON r.id = op.role_id AND op.is_active = true
LEFT JOIN sys_object_metadata o ON op.object_id = o.id
WHERE u.username = 'customer_admin_user'  -- Change to test different users
ORDER BY r.role_name, o.api_name;


-- ============================================================================
-- EXPECTED OUTPUT
-- ============================================================================
/*
System Roles:
- customer_admin (system role, active) - Full access
- customer_user (system role, active) - Team-level access

Custom Roles (examples):
- sales_manager (custom role, active)
- sales_rep (custom role, active)

Permissions (per object):
- customer_admin → all_objects: ["data:*", "bulk:*", "query:*", "schema:modify", "field:*"]
- customer_user → all_objects: ["data:read:scope:team", "data:create", ...] + row_filter

User-Role Assignments:
- customer_admin_user → customer_admin role
- customer_regular_user → customer_user role
*/
