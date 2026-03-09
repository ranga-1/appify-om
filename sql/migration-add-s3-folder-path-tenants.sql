-- Migration: Add s3_folder_path to tenant schemas
-- Run this on the TENANTS database for all tenant_* schemas
-- Only updates schemas that already have sys_object_metadata table

DO $$
DECLARE
    tenant_schema TEXT;
    table_exists BOOLEAN;
BEGIN
    -- Loop through all tenant schemas that have sys_object_metadata table
    FOR tenant_schema IN 
        SELECT DISTINCT table_schema
        FROM information_schema.tables
        WHERE table_schema LIKE 'tenant_%'
          AND table_name = 'sys_object_metadata'
        ORDER BY table_schema
    LOOP
        -- Add s3_folder_path column to each tenant's sys_object_metadata table
        EXECUTE format(
            'ALTER TABLE %I.sys_object_metadata ADD COLUMN IF NOT EXISTS s3_folder_path TEXT',
            tenant_schema
        );
        
        RAISE NOTICE 'Added s3_folder_path to %.sys_object_metadata', tenant_schema;
    END LOOP;
    
    -- Report if no tables were found
    IF NOT FOUND THEN
        RAISE NOTICE 'No tenant schemas with sys_object_metadata table found. This is normal if no tenants have used Object Modeler yet.';
    END IF;
END $$;

-- Verify columns added to all tenant schemas
SELECT 
    table_schema, 
    column_name,
    data_type
FROM information_schema.columns 
WHERE table_name = 'sys_object_metadata' 
  AND column_name = 's3_folder_path' 
  AND table_schema LIKE 'tenant_%'
ORDER BY table_schema;
