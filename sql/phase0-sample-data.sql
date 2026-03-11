-- ============================================================================
-- PHASE 0: Sample Data for Testing Permission System
-- ============================================================================
-- Purpose: Bootstrap default roles, sample users, and permissions for testing
--
-- EXECUTION INSTRUCTIONS:
-- 1. Connect to your test database
-- 2. Set schema: SET search_path TO tenant_abc123; (or public for core)
-- 3. Run this script
-- 4. Verify by querying the tables
--
-- NOTE: Replace UUIDs and email addresses with your actual test data
-- ============================================================================

-- System user UUID for created_by/modified_by
-- 00000000-0000-0000-0000-000000000000 = SYSTEM

-- ============================================================================
-- STEP 1: Create Sample Roles
-- ============================================================================

-- Admin role - Full access
INSERT INTO sys_roles (role_name, description, is_system_role, is_active, created_by, modified_by)
VALUES 
    ('admin', 'Full administrative access to all objects and operations', true, true, 
     '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    
    ('developer', 'Developer access - can create/modify objects and deploy', true, true,
     '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    
    ('analyst', 'Data analyst - read-only with advanced querying', true, true,
     '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    
    ('sales_rep', 'Sales representative - team-level data access', true, true,
     '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    
    ('viewer', 'Read-only viewer - basic access', true, true,
     '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000')
ON CONFLICT (role_name) DO NOTHING;


-- ============================================================================
-- STEP 2: Create Sample User (Optional - for testing)
-- ============================================================================
-- NOTE: Replace these UUIDs and details with actual test user data from Keycloak

INSERT INTO sys_users (user_id, email, username, first_name, last_name, full_name, is_active, created_by, modified_by)
VALUES 
    ('11111111-1111-1111-1111-111111111111', 'admin@test.com', 'admin_user', 'Admin', 'User', 'Admin User', true,
     '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    
    ('22222222-2222-2222-2222-222222222222', 'sales@test.com', 'sales_user', 'Sales', 'Rep', 'Sales Rep', true,
     '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    
    ('33333333-3333-3333-3333-333333333333', 'analyst@test.com', 'analyst_user', 'Data', 'Analyst', 'Data Analyst', true,
     '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000')
ON CONFLICT (user_id) DO NOTHING;


-- ============================================================================
-- STEP 3: Assign Roles to Users
-- ============================================================================

-- Assign admin role to admin user
INSERT INTO sys_user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id as user_id,
    r.id as role_id,
    '00000000-0000-0000-0000-000000000000' as assigned_by
FROM sys_users u
CROSS JOIN sys_roles r
WHERE u.username = 'admin_user' AND r.role_name = 'admin'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Assign sales_rep role to sales user
INSERT INTO sys_user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id as user_id,
    r.id as role_id,
    '00000000-0000-0000-0000-000000000000' as assigned_by
FROM sys_users u
CROSS JOIN sys_roles r
WHERE u.username = 'sales_user' AND r.role_name = 'sales_rep'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Assign analyst role to analyst user
INSERT INTO sys_user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id as user_id,
    r.id as role_id,
    '00000000-0000-0000-0000-000000000000' as assigned_by
FROM sys_users u
CROSS JOIN sys_roles r
WHERE u.username = 'analyst_user' AND r.role_name = 'analyst'
ON CONFLICT (user_id, role_id) DO NOTHING;


-- ============================================================================
-- STEP 4: Create Object Permissions
-- ============================================================================
-- NOTE: This assumes you have objects in sys_object_metadata
-- Replace 'abc12_customer_account' with your actual object api_name

-- Admin role permissions - Full access to all operations
INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    '["data:*", "bulk:*", "query:*", "schema:*", "admin:*", "field:*"]'::jsonb as permissions,
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'admin'
  AND o.api_name LIKE '%customer%'  -- Adjust filter to match your objects
LIMIT 1
ON CONFLICT (role_id, object_id) DO NOTHING;

-- Sales Rep permissions - Team-level access with field restrictions
INSERT INTO sys_object_permissions (role_id, object_id, permissions, row_filter, field_permissions, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    '["data:read:scope:team", "data:create", "data:update:scope:self", "query:basic", "bulk:export:format:csv", "field:read:*"]'::jsonb as permissions,
    'created_by = $user_id OR assigned_to = $user_id' as row_filter,
    '{"salary": {"access": "mask"}, "ssn": {"access": "hide"}}'::jsonb as field_permissions,
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'sales_rep'
  AND o.api_name LIKE '%customer%'
LIMIT 1
ON CONFLICT (role_id, object_id) DO NOTHING;

-- Analyst permissions - Read-only with advanced querying
INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    '["data:read:scope:all", "query:advanced", "query:aggregation", "bulk:export:format:*", "field:read:*"]'::jsonb as permissions,
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'analyst'
  AND o.api_name LIKE '%customer%'
LIMIT 1
ON CONFLICT (role_id, object_id) DO NOTHING;

-- Viewer permissions - Basic read-only
INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    '["data:read:scope:self", "query:basic", "field:read:*"]'::jsonb as permissions,
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'viewer'
  AND o.api_name LIKE '%customer%'
LIMIT 1
ON CONFLICT (role_id, object_id) DO NOTHING;


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check roles created
SELECT 
    role_name, 
    description, 
    is_system_role, 
    is_active,
    created_date
FROM sys_roles
ORDER BY role_name;

-- Check users created
SELECT 
    username,
    email,
    full_name,
    is_active,
    created_date
FROM sys_users
ORDER BY username;

-- Check user-role assignments
SELECT 
    u.username,
    u.email,
    r.role_name,
    ur.assigned_date,
    ur.is_active
FROM sys_user_roles ur
JOIN sys_users u ON ur.user_id = u.id
JOIN sys_roles r ON ur.role_id = r.id
ORDER BY u.username, r.role_name;

-- Check object permissions
SELECT 
    r.role_name,
    o.api_name as object_name,
    op.permissions,
    op.row_filter,
    op.field_permissions,
    op.is_active
FROM sys_object_permissions op
JOIN sys_roles r ON op.role_id = r.id
JOIN sys_object_metadata o ON op.object_id = o.id
ORDER BY r.role_name, o.api_name;

-- Full permission resolution for a user (example: admin_user)
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
WHERE u.username = 'admin_user'
ORDER BY r.role_name, o.api_name;


-- ============================================================================
-- CLEANUP (Optional - uncomment to remove test data)
-- ============================================================================
/*
DELETE FROM sys_object_permissions WHERE role_id IN (SELECT id FROM sys_roles WHERE is_system_role = true);
DELETE FROM sys_user_roles;
DELETE FROM sys_roles WHERE is_system_role = true;
DELETE FROM sys_users WHERE username IN ('admin_user', 'sales_user', 'analyst_user');
*/
