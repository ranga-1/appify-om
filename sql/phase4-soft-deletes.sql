-- Phase 4: Soft Delete System
-- 
-- Implements recoverable deletions by marking records as deleted instead of
-- permanently removing them from the database.

-- ============================================================================
-- Soft Delete Columns
-- ============================================================================

-- These columns should be added to all tenant data tables
-- The migration will be handled programmatically to add these to existing tables

-- Example for a typical data table:
-- ALTER TABLE {schema}.{table_name} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE;
-- ALTER TABLE {schema}.{table_name} ADD COLUMN IF NOT EXISTS deleted_by UUID;

-- ============================================================================
-- Soft Delete Configuration
-- ============================================================================

CREATE TABLE IF NOT EXISTS sys_soft_delete_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(50) NOT NULL,
    object_id UUID NOT NULL REFERENCES sys_object_metadata(id),
    
    -- Soft delete settings
    enabled BOOLEAN DEFAULT true,
    permanent_delete_after_days INTEGER, -- NULL means never permanently delete
    
    -- Recovery settings
    allow_undelete BOOLEAN DEFAULT true,
    require_permission_to_undelete BOOLEAN DEFAULT true,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id, object_id)
);

CREATE INDEX idx_soft_delete_config_tenant ON sys_soft_delete_config(tenant_id);
CREATE INDEX idx_soft_delete_config_object ON sys_soft_delete_config(object_id);

COMMENT ON TABLE sys_soft_delete_config IS 'Configuration for soft delete behavior per object';
COMMENT ON COLUMN sys_soft_delete_config.permanent_delete_after_days IS 'Days before permanently deleting soft-deleted records (NULL = never)';


-- ============================================================================
-- Deleted Records Tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS sys_deleted_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    tenant_id VARCHAR(50) NOT NULL,
    object_id UUID NOT NULL,
    object_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,
    
    -- Deletion context
    deleted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_by UUID NOT NULL,
    deletion_reason TEXT,
    
    -- Recovery tracking
    undeleted_at TIMESTAMP WITH TIME ZONE,
    undeleted_by UUID,
    undelete_reason TEXT,
    
    -- Permanent deletion tracking
    permanent_delete_scheduled_at TIMESTAMP WITH TIME ZONE,
    permanently_deleted_at TIMESTAMP WITH TIME ZONE,
    
    -- Snapshot of deleted data (for verification before permanent delete)
    data_snapshot JSONB,
    
    UNIQUE(tenant_id, object_name, record_id)
);

CREATE INDEX idx_deleted_records_tenant ON sys_deleted_records(tenant_id);
CREATE INDEX idx_deleted_records_object ON sys_deleted_records(object_name);
CREATE INDEX idx_deleted_records_deleted_at ON sys_deleted_records(deleted_at);
CREATE INDEX idx_deleted_records_scheduled ON sys_deleted_records(permanent_delete_scheduled_at) 
    WHERE permanent_delete_scheduled_at IS NOT NULL 
      AND permanently_deleted_at IS NULL;

COMMENT ON TABLE sys_deleted_records IS 'Track all soft-deleted records for recovery and permanent deletion';


-- ============================================================================
-- Soft Delete Helper Functions
-- ============================================================================

-- Mark record as deleted (soft delete)
CREATE OR REPLACE FUNCTION soft_delete_record(
    p_schema_name VARCHAR(50),
    p_table_name VARCHAR(100),
    p_record_id UUID,
    p_deleted_by UUID,
    p_deletion_reason TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_sql TEXT;
    v_rows_affected INTEGER;
BEGIN
    -- Update the record to mark as deleted
    v_sql := format(
        'UPDATE %I.%I SET deleted_at = CURRENT_TIMESTAMP, deleted_by = %L WHERE id = %L AND deleted_at IS NULL',
        p_schema_name,
        p_table_name,
        p_deleted_by,
        p_record_id
    );
    
    EXECUTE v_sql;
    GET DIAGNOSTICS v_rows_affected = ROW_COUNT;
    
    IF v_rows_affected > 0 THEN
        -- Record the deletion in tracking table
        INSERT INTO sys_deleted_records (
            tenant_id,
            object_name,
            record_id,
            deleted_by,
            deletion_reason
        ) VALUES (
            p_schema_name,
            p_table_name,
            p_record_id,
            p_deleted_by,
            p_deletion_reason
        );
        
        RETURN true;
    ELSE
        RETURN false;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION soft_delete_record IS 'Soft delete a record by setting deleted_at timestamp';


-- Undelete a soft-deleted record
CREATE OR REPLACE FUNCTION undelete_record(
    p_schema_name VARCHAR(50),
    p_table_name VARCHAR(100),
    p_record_id UUID,
    p_undeleted_by UUID,
    p_undelete_reason TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_sql TEXT;
    v_rows_affected INTEGER;
BEGIN
    -- Check if undelete is allowed
    IF NOT EXISTS (
        SELECT 1 FROM sys_soft_delete_config c
        JOIN sys_object_metadata m ON c.object_id = m.id
        WHERE m.table_name = p_table_name
          AND c.tenant_id = p_schema_name
          AND c.allow_undelete = true
    ) THEN
        RAISE EXCEPTION 'Undelete is not allowed for this object';
    END IF;
    
    -- Restore the record
    v_sql := format(
        'UPDATE %I.%I SET deleted_at = NULL, deleted_by = NULL WHERE id = %L AND deleted_at IS NOT NULL',
        p_schema_name,
        p_table_name,
        p_record_id
    );
    
    EXECUTE v_sql;
    GET DIAGNOSTICS v_rows_affected = ROW_COUNT;
    
    IF v_rows_affected > 0 THEN
        -- Update the tracking record
        UPDATE sys_deleted_records
        SET undeleted_at = CURRENT_TIMESTAMP,
            undeleted_by = p_undeleted_by,
            undelete_reason = p_undelete_reason
        WHERE tenant_id = p_schema_name
          AND object_name = p_table_name
          AND record_id = p_record_id;
        
        RETURN true;
    ELSE
        RETURN false;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION undelete_record IS 'Restore a soft-deleted record';


-- Permanently delete old soft-deleted records
CREATE OR REPLACE FUNCTION permanent_delete_old_records()
RETURNS INTEGER AS $$
DECLARE
    v_record RECORD;
    v_sql TEXT;
    v_deleted_count INTEGER := 0;
BEGIN
    -- Find records eligible for permanent deletion
    FOR v_record IN
        SELECT 
            dr.tenant_id,
            dr.object_name,
            dr.record_id,
            c.permanent_delete_after_days
        FROM sys_deleted_records dr
        JOIN sys_object_metadata m ON dr.object_name = m.table_name
        JOIN sys_soft_delete_config c ON m.id = c.object_id
        WHERE dr.permanently_deleted_at IS NULL
          AND dr.undeleted_at IS NULL  -- Not restored
          AND c.permanent_delete_after_days IS NOT NULL
          AND dr.deleted_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * c.permanent_delete_after_days
    LOOP
        -- Permanently delete the record
        v_sql := format(
            'DELETE FROM %I.%I WHERE id = %L',
            v_record.tenant_id,
            v_record.object_name,
            v_record.record_id
        );
        
        EXECUTE v_sql;
        
        -- Mark as permanently deleted
        UPDATE sys_deleted_records
        SET permanently_deleted_at = CURRENT_TIMESTAMP
        WHERE tenant_id = v_record.tenant_id
          AND object_name = v_record.object_name
          AND record_id = v_record.record_id;
        
        v_deleted_count := v_deleted_count + 1;
    END LOOP;
    
    RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION permanent_delete_old_records IS 'Permanently delete records past retention period';


-- Get deleted records for an object
CREATE OR REPLACE FUNCTION get_deleted_records(
    p_tenant_id VARCHAR(50),
    p_object_name VARCHAR(100),
    p_include_restored BOOLEAN DEFAULT false,
    p_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    record_id UUID,
    deleted_at TIMESTAMP WITH TIME ZONE,
    deleted_by UUID,
    deletion_reason TEXT,
    undeleted_at TIMESTAMP WITH TIME ZONE,
    undeleted_by UUID,
    days_until_permanent_delete INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dr.record_id,
        dr.deleted_at,
        dr.deleted_by,
        dr.deletion_reason,
        dr.undeleted_at,
        dr.undeleted_by,
        CASE 
            WHEN c.permanent_delete_after_days IS NOT NULL THEN
                c.permanent_delete_after_days - 
                EXTRACT(DAY FROM CURRENT_TIMESTAMP - dr.deleted_at)::INTEGER
            ELSE NULL
        END as days_until_permanent_delete
    FROM sys_deleted_records dr
    JOIN sys_object_metadata m ON dr.object_name = m.table_name
    LEFT JOIN sys_soft_delete_config c ON m.id = c.object_id AND c.tenant_id = p_tenant_id
    WHERE dr.tenant_id = p_tenant_id
      AND dr.object_name = p_object_name
      AND dr.permanently_deleted_at IS NULL
      AND (p_include_restored OR dr.undeleted_at IS NULL)
    ORDER BY dr.deleted_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_deleted_records IS 'Get list of deleted records with restore information';


-- ============================================================================
-- Migration Function to Add Soft Delete Columns
-- ============================================================================

CREATE OR REPLACE FUNCTION add_soft_delete_columns_to_table(
    p_schema_name VARCHAR(50),
    p_table_name VARCHAR(100)
)
RETURNS BOOLEAN AS $$
DECLARE
    v_sql TEXT;
BEGIN
    -- Add deleted_at column if it doesn't exist
    v_sql := format(
        'ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE',
        p_schema_name,
        p_table_name
    );
    EXECUTE v_sql;
    
    -- Add deleted_by column if it doesn't exist
    v_sql := format(
        'ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS deleted_by UUID',
        p_schema_name,
        p_table_name
    );
    EXECUTE v_sql;
    
    -- Create index on deleted_at for efficient filtering
    v_sql := format(
        'CREATE INDEX IF NOT EXISTS idx_%I_deleted_at ON %I.%I(deleted_at) WHERE deleted_at IS NOT NULL',
        p_table_name,
        p_schema_name,
        p_table_name
    );
    EXECUTE v_sql;
    
    RETURN true;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error adding soft delete columns: %', SQLERRM;
        RETURN false;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION add_soft_delete_columns_to_table IS 'Add soft delete columns to existing table';
