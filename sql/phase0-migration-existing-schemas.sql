-- ============================================================================
-- PHASE 0: Migration Script - Add Permission Tables to Existing Schemas
-- ============================================================================
-- Purpose: Add sys_roles, sys_user_roles, and sys_object_permissions tables
--          to existing tenant schemas and unshackle_core public schema
--
-- MANUAL EXECUTION INSTRUCTIONS:
-- 1. Connect to unshackle_core database
-- 2. Run this script for EACH schema that needs the tables:
--    - public schema (for core database permissions)
--    - Each tenant_* schema (for tenant-specific permissions)
--
-- OPTION 1: Run for specific schema (recommended for testing)
--    SET search_path TO tenant_abc123;  -- Replace with your schema
--    -- Then run the CREATE TABLE statements below
--
-- OPTION 2: Run for all tenant schemas at once (use with caution)
--    -- Uncomment and run the DO block at the bottom
-- ============================================================================

-- Note: sys_users table already exists, so we only add the 3 new tables:
-- 1. sys_roles
-- 2. sys_user_roles
-- 3. sys_object_permissions


-- ============================================================================
-- TABLE 1: sys_roles
-- ============================================================================
CREATE TABLE IF NOT EXISTS sys_roles
(
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    keycloak_role_id uuid,
    role_name text NOT NULL,
    description text,
    is_system_role boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_by uuid NOT NULL,
    created_date timestamp with time zone NOT NULL DEFAULT now(),
    modified_by uuid NOT NULL,
    modified_date timestamp with time zone NOT NULL DEFAULT now(),
    audit_info jsonb,
    CONSTRAINT sys_roles_pkey PRIMARY KEY (id),
    CONSTRAINT sys_roles_role_name_key UNIQUE (role_name),
    CONSTRAINT valid_role_name CHECK (role_name ~ '^[a-z][a-z0-9_]*$'::text),
    CONSTRAINT valid_audit_info CHECK (audit_info IS NULL OR jsonb_typeof(audit_info) = 'object'::text)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_roles_role_name ON sys_roles USING btree (role_name);
CREATE INDEX IF NOT EXISTS idx_sys_roles_keycloak_role_id ON sys_roles USING btree (keycloak_role_id);
CREATE INDEX IF NOT EXISTS idx_sys_roles_is_active ON sys_roles USING btree (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sys_roles_is_system_role ON sys_roles USING btree (is_system_role) WHERE is_system_role = true;
CREATE INDEX IF NOT EXISTS idx_sys_roles_created_date ON sys_roles USING btree (created_date DESC);
CREATE INDEX IF NOT EXISTS idx_sys_roles_modified_date ON sys_roles USING btree (modified_date DESC);
CREATE INDEX IF NOT EXISTS idx_sys_roles_audit_info ON sys_roles USING gin (audit_info);

CREATE TRIGGER trg_sys_roles_modified_date
    BEFORE UPDATE ON sys_roles
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_date();

COMMENT ON TABLE sys_roles IS 'Defines roles available in this schema/database for permission assignment';
COMMENT ON COLUMN sys_roles.keycloak_role_id IS 'Optional UUID linking to Keycloak role for synchronization';
COMMENT ON COLUMN sys_roles.is_system_role IS 'True for built-in roles (admin, viewer), false for custom roles';


-- ============================================================================
-- TABLE 2: sys_user_roles
-- ============================================================================
CREATE TABLE IF NOT EXISTS sys_user_roles
(
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    role_id uuid NOT NULL,
    assigned_by uuid NOT NULL,
    assigned_date timestamp with time zone NOT NULL DEFAULT now(),
    expires_date timestamp with time zone,
    is_active boolean NOT NULL DEFAULT true,
    metadata jsonb,
    CONSTRAINT sys_user_roles_pkey PRIMARY KEY (id),
    CONSTRAINT sys_user_roles_user_role_key UNIQUE (user_id, role_id),
    CONSTRAINT sys_user_roles_user_fkey FOREIGN KEY (user_id) REFERENCES sys_users(id) ON DELETE CASCADE,
    CONSTRAINT sys_user_roles_role_fkey FOREIGN KEY (role_id) REFERENCES sys_roles(id) ON DELETE CASCADE,
    CONSTRAINT valid_metadata CHECK (metadata IS NULL OR jsonb_typeof(metadata) = 'object'::text)
);

CREATE INDEX IF NOT EXISTS idx_sys_user_roles_user_id ON sys_user_roles USING btree (user_id);
CREATE INDEX IF NOT EXISTS idx_sys_user_roles_role_id ON sys_user_roles USING btree (role_id);
CREATE INDEX IF NOT EXISTS idx_sys_user_roles_assigned_by ON sys_user_roles USING btree (assigned_by);
CREATE INDEX IF NOT EXISTS idx_sys_user_roles_assigned_date ON sys_user_roles USING btree (assigned_date DESC);
CREATE INDEX IF NOT EXISTS idx_sys_user_roles_is_active ON sys_user_roles USING btree (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sys_user_roles_expires_date ON sys_user_roles USING btree (expires_date) WHERE expires_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sys_user_roles_metadata ON sys_user_roles USING gin (metadata);

COMMENT ON TABLE sys_user_roles IS 'Many-to-many mapping between users and roles for permission assignment';
COMMENT ON COLUMN sys_user_roles.expires_date IS 'Optional expiration date for temporary role assignments';


-- ============================================================================
-- TABLE 3: sys_object_permissions
-- ============================================================================
CREATE TABLE IF NOT EXISTS sys_object_permissions
(
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    role_id uuid NOT NULL,
    object_id uuid NOT NULL,
    permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
    row_filter text,
    field_permissions jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_by uuid NOT NULL,
    created_date timestamp with time zone NOT NULL DEFAULT now(),
    modified_by uuid NOT NULL,
    modified_date timestamp with time zone NOT NULL DEFAULT now(),
    audit_info jsonb,
    CONSTRAINT sys_object_permissions_pkey PRIMARY KEY (id),
    CONSTRAINT sys_object_permissions_role_object_key UNIQUE (role_id, object_id),
    CONSTRAINT sys_object_permissions_role_fkey FOREIGN KEY (role_id) REFERENCES sys_roles(id) ON DELETE CASCADE,
    CONSTRAINT sys_object_permissions_object_fkey FOREIGN KEY (object_id) REFERENCES sys_object_metadata(id) ON DELETE CASCADE,
    CONSTRAINT valid_permissions CHECK (jsonb_typeof(permissions) = 'array'::text),
    CONSTRAINT valid_field_permissions CHECK (field_permissions IS NULL OR jsonb_typeof(field_permissions) = 'object'::text),
    CONSTRAINT valid_audit_info CHECK (audit_info IS NULL OR jsonb_typeof(audit_info) = 'object'::text)
);

CREATE INDEX IF NOT EXISTS idx_sys_object_permissions_role_id ON sys_object_permissions USING btree (role_id);
CREATE INDEX IF NOT EXISTS idx_sys_object_permissions_object_id ON sys_object_permissions USING btree (object_id);
CREATE INDEX IF NOT EXISTS idx_sys_object_permissions_is_active ON sys_object_permissions USING btree (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sys_object_permissions_permissions ON sys_object_permissions USING gin (permissions);
CREATE INDEX IF NOT EXISTS idx_sys_object_permissions_field_permissions ON sys_object_permissions USING gin (field_permissions);
CREATE INDEX IF NOT EXISTS idx_sys_object_permissions_created_date ON sys_object_permissions USING btree (created_date DESC);
CREATE INDEX IF NOT EXISTS idx_sys_object_permissions_modified_date ON sys_object_permissions USING btree (modified_date DESC);
CREATE INDEX IF NOT EXISTS idx_sys_object_permissions_audit_info ON sys_object_permissions USING gin (audit_info);

CREATE TRIGGER trg_sys_object_permissions_modified_date
    BEFORE UPDATE ON sys_object_permissions
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_date();

COMMENT ON TABLE sys_object_permissions IS 'Stores IAM-style permissions for each role on each object (data API access control)';
COMMENT ON COLUMN sys_object_permissions.permissions IS 'Array of permission strings like ["data:read:scope:all", "query:advanced", "bulk:export:format:csv"]';
COMMENT ON COLUMN sys_object_permissions.row_filter IS 'Optional SQL WHERE clause template for row-level security (e.g., "created_by = $user_id")';
COMMENT ON COLUMN sys_object_permissions.field_permissions IS 'Optional field-level overrides: {"field_name": {"access": "read|write|mask|hide"}}';


-- ============================================================================
-- VERIFICATION
-- ============================================================================
-- Run this to verify tables were created successfully
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE columns.table_name = tables.table_name) as column_count
FROM information_schema.tables
WHERE table_schema = current_schema()
  AND table_name IN ('sys_roles', 'sys_user_roles', 'sys_object_permissions')
ORDER BY table_name;


-- ============================================================================
-- OPTION 2: Automated Migration for All Tenant Schemas
-- ============================================================================
-- WARNING: Use this carefully! It will modify ALL tenant schemas at once.
-- Uncomment the block below to run for all tenant schemas automatically.
/*
DO $$
DECLARE
    tenant_record RECORD;
    schema_name TEXT;
BEGIN
    -- Add to public schema first (for core database)
    RAISE NOTICE 'Adding permission tables to public schema...';
    SET search_path TO public;
    -- (Paste the CREATE TABLE statements here if running automated migration)
    
    -- Add to all tenant schemas
    FOR tenant_record IN 
        SELECT tenant_id FROM public.tenant_registry WHERE status = 'active'
    LOOP
        schema_name := 'tenant_' || tenant_record.tenant_id;
        
        RAISE NOTICE 'Adding permission tables to schema: %', schema_name;
        
        EXECUTE format('SET search_path TO %I', schema_name);
        
        -- sys_roles
        EXECUTE 'CREATE TABLE IF NOT EXISTS sys_roles (...)';  -- Full CREATE statement
        
        -- sys_user_roles
        EXECUTE 'CREATE TABLE IF NOT EXISTS sys_user_roles (...)';  -- Full CREATE statement
        
        -- sys_object_permissions
        EXECUTE 'CREATE TABLE IF NOT EXISTS sys_object_permissions (...)';  -- Full CREATE statement
        
        RAISE NOTICE 'Completed schema: %', schema_name;
    END LOOP;
    
    RAISE NOTICE 'Migration completed for all schemas';
END $$;
*/


-- ============================================================================
-- MANUAL EXECUTION EXAMPLE
-- ============================================================================
/*
-- Step 1: Add to public schema (for core database permissions)
SET search_path TO public;
-- (Paste the CREATE TABLE statements above)

-- Step 2: Add to each tenant schema one by one
SET search_path TO tenant_abc123;
-- (Paste the CREATE TABLE statements above)

-- Step 3: Verify
SELECT table_name, column_count FROM ...
*/
