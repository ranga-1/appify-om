-- ============================================================================
-- PHASE 0: Core Database Bootstrap - System Roles & Permissions
-- ============================================================================
-- Database: unshackle_core
-- Schema: public
-- Purpose: Create system roles for core database access (tenant_registry, etc.)
--
-- EXECUTION INSTRUCTIONS:
-- 1. Connect to unshackle_core database
-- 2. Run: SET search_path TO public;
-- 3. Run this script
-- ============================================================================

SET search_path TO public;

-- System user UUID for created_by/modified_by
-- 00000000-0000-0000-0000-000000000000 = SYSTEM

-- ============================================================================
-- SYSTEM ROLES (Core Database)
-- ============================================================================

-- appify-admin: Full platform administrative access
INSERT INTO sys_roles (role_name, description, is_system_role, is_active, created_by, modified_by)
VALUES 
    ('appify_admin', 
     'Appify platform administrator - full access to all core database operations including tenant management, system configuration, and platform monitoring', 
     true, 
     true, 
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000'),
    
    ('appify_user', 
     'Appify platform user - read-only access to core database for monitoring and basic operations', 
     true, 
     true,
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000')
ON CONFLICT (role_name) DO NOTHING;


-- ============================================================================
-- PERMISSIONS: appify_admin Role
-- ============================================================================
-- Full access to all core database objects

INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    jsonb_build_array(
        'data:*',              -- All data operations
        'bulk:*',              -- All bulk operations
        'query:*',             -- All query types
        'schema:*',            -- Schema management
        'admin:*',             -- Admin operations
        'field:*'              -- All field access
    ) as permissions,
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'appify_admin'
  AND o.api_name = 'tenant_registry'
ON CONFLICT (role_id, object_id) DO UPDATE
SET permissions = EXCLUDED.permissions,
    modified_date = now();


-- ============================================================================
-- PERMISSIONS: appify_user Role
-- ============================================================================
-- Read-only access to core database

INSERT INTO sys_object_permissions (role_id, object_id, permissions, created_by, modified_by)
SELECT 
    r.id as role_id,
    o.id as object_id,
    jsonb_build_array(
        'data:read:scope:all',     -- Read all records
        'query:basic',              -- Basic queries only
        'field:read:*'              -- Read all fields
    ) as permissions,
    '00000000-0000-0000-0000-000000000000' as created_by,
    '00000000-0000-0000-0000-000000000000' as modified_by
FROM sys_roles r
CROSS JOIN sys_object_metadata o
WHERE r.role_name = 'appify_user'
  AND o.api_name = 'tenant_registry'
ON CONFLICT (role_id, object_id) DO UPDATE
SET permissions = EXCLUDED.permissions,
    modified_date = now();


-- ============================================================================
-- SAMPLE USER (Optional - for testing)
-- ============================================================================
-- Replace UUIDs and email with actual Keycloak user data

INSERT INTO sys_users (user_id, email, username, first_name, last_name, full_name, is_active, created_by, modified_by)
VALUES 
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 
     'platform.admin@appify.com', 
     'platform_admin', 
     'Platform', 
     'Admin', 
     'Platform Admin', 
     true,
     '00000000-0000-0000-0000-000000000000', 
     '00000000-0000-0000-0000-000000000000')
ON CONFLICT (user_id) DO NOTHING;

-- Assign appify_admin role to sample user
INSERT INTO sys_user_roles (user_id, role_id, assigned_by)
SELECT 
    u.id as user_id,
    r.id as role_id,
    '00000000-0000-0000-0000-000000000000' as assigned_by
FROM sys_users u
CROSS JOIN sys_roles r
WHERE u.username = 'ranga@appify.com' 
  AND r.role_name = 'appify_admin'
ON CONFLICT (user_id, role_id) DO NOTHING;


-- ============================================================================
-- VERIFICATION
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

-- Check object metadata
SELECT 
    api_name,
    label,
    status,
    created_date
FROM sys_object_metadata
ORDER BY api_name;

-- Check permissions
SELECT 
    r.role_name,
    o.api_name as object_name,
    op.permissions,
    op.is_active
FROM sys_object_permissions op
JOIN sys_roles r ON op.role_id = r.id
JOIN sys_object_metadata o ON op.object_id = o.id
ORDER BY r.role_name, o.api_name;

-- Full permission resolution (if sample user exists)
SELECT 
    u.username,
    u.email,
    r.role_name,
    o.api_name as object_name,
    op.permissions
FROM sys_users u
JOIN sys_user_roles ur ON u.id = ur.user_id AND ur.is_active = true
JOIN sys_roles r ON ur.role_id = r.id AND r.is_active = true
LEFT JOIN sys_object_permissions op ON r.id = op.role_id AND op.is_active = true
LEFT JOIN sys_object_metadata o ON op.object_id = o.id
WHERE u.username = 'platform_admin'
ORDER BY r.role_name, o.api_name;


-- ============================================================================
-- EXPECTED OUTPUT
-- ============================================================================
/*
Roles:
- appify_admin (system role, active)
- appify_user (system role, active)

Object Metadata:
- tenant_registry (core table)

Permissions:
- appify_admin → tenant_registry: ["data:*", "bulk:*", "query:*", "schema:*", "admin:*", "field:*"]
- appify_user → tenant_registry: ["data:read:scope:all", "query:basic", "field:read:*"]

User-Role Assignment (if sample user created):
- platform_admin → appify_admin role
*/
