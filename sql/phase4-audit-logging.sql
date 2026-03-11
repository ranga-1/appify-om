-- Phase 4: Audit Logging System
-- 
-- This schema tracks all data operations for compliance, security, and debugging.
-- Every CRUD operation on tenant data is logged with full context.

-- ============================================================================
-- Audit Log Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS sys_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Context
    tenant_id VARCHAR(50) NOT NULL,
    user_id UUID NOT NULL,
    session_id UUID,
    
    -- Operation Details
    action VARCHAR(20) NOT NULL, -- create, read, update, delete, bulk_create, bulk_update, bulk_delete, export, import
    object_id UUID NOT NULL, -- Reference to sys_object_metadata
    object_name VARCHAR(100) NOT NULL,
    record_id UUID, -- NULL for bulk operations
    
    -- Change Tracking
    old_values JSONB, -- Previous state (for update/delete)
    new_values JSONB, -- New state (for create/update)
    changed_fields TEXT[], -- List of fields that changed
    
    -- Request Context
    ip_address INET,
    user_agent TEXT,
    request_id UUID,
    endpoint VARCHAR(255),
    http_method VARCHAR(10),
    
    -- Result
    status VARCHAR(20) NOT NULL, -- success, failed, partial
    error_message TEXT,
    affected_count INTEGER DEFAULT 1, -- For bulk operations
    
    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER, -- Time taken to execute operation
    
    -- Metadata
    metadata JSONB -- Additional context (filters for bulk ops, etc.)
);

-- Indexes for efficient querying
CREATE INDEX idx_audit_log_tenant_id ON sys_audit_log(tenant_id);
CREATE INDEX idx_audit_log_user_id ON sys_audit_log(user_id);
CREATE INDEX idx_audit_log_object_name ON sys_audit_log(object_name);
CREATE INDEX idx_audit_log_record_id ON sys_audit_log(record_id) WHERE record_id IS NOT NULL;
CREATE INDEX idx_audit_log_action ON sys_audit_log(action);
CREATE INDEX idx_audit_log_created_at ON sys_audit_log(created_at DESC);
CREATE INDEX idx_audit_log_status ON sys_audit_log(status);

-- Composite indexes for common queries
CREATE INDEX idx_audit_log_tenant_object_date 
    ON sys_audit_log(tenant_id, object_name, created_at DESC);
CREATE INDEX idx_audit_log_user_action_date 
    ON sys_audit_log(user_id, action, created_at DESC);

-- Partial index for failed operations
CREATE INDEX idx_audit_log_failed 
    ON sys_audit_log(tenant_id, created_at DESC) 
    WHERE status = 'failed';

COMMENT ON TABLE sys_audit_log IS 'Audit trail for all data operations';
COMMENT ON COLUMN sys_audit_log.action IS 'Type of operation performed';
COMMENT ON COLUMN sys_audit_log.old_values IS 'State before operation (update/delete)';
COMMENT ON COLUMN sys_audit_log.new_values IS 'State after operation (create/update)';
COMMENT ON COLUMN sys_audit_log.changed_fields IS 'List of field names that were modified';
COMMENT ON COLUMN sys_audit_log.affected_count IS 'Number of records affected (for bulk operations)';


-- ============================================================================
-- Audit Log Retention Policy
-- ============================================================================

CREATE TABLE IF NOT EXISTS sys_audit_retention_policy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(50) NOT NULL,
    object_name VARCHAR(100), -- NULL means applies to all objects
    
    retention_days INTEGER NOT NULL DEFAULT 365, -- How long to keep audit logs
    archive_enabled BOOLEAN DEFAULT false, -- Whether to archive before deletion
    archive_storage VARCHAR(255), -- S3 bucket or other storage location
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id, object_name)
);

CREATE INDEX idx_audit_retention_tenant ON sys_audit_retention_policy(tenant_id);

COMMENT ON TABLE sys_audit_retention_policy IS 'Configurable retention policies for audit logs';


-- ============================================================================
-- Audit Log Cleanup Function
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_old_audit_logs()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Delete audit logs older than retention period
    WITH retention_config AS (
        SELECT 
            tenant_id,
            object_name,
            retention_days
        FROM sys_audit_retention_policy
    ),
    to_delete AS (
        DELETE FROM sys_audit_log
        WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * (
            SELECT COALESCE(
                (SELECT retention_days 
                 FROM retention_config 
                 WHERE retention_config.tenant_id = sys_audit_log.tenant_id 
                   AND retention_config.object_name = sys_audit_log.object_name),
                (SELECT retention_days 
                 FROM retention_config 
                 WHERE retention_config.tenant_id = sys_audit_log.tenant_id 
                   AND retention_config.object_name IS NULL),
                365 -- Default to 1 year if no policy exists
            )
        )
        RETURNING *
    )
    SELECT COUNT(*) INTO deleted_count FROM to_delete;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_audit_logs IS 'Cleanup audit logs based on retention policies';


-- ============================================================================
-- Audit Query Functions
-- ============================================================================

-- Get audit trail for a specific record
CREATE OR REPLACE FUNCTION get_record_audit_trail(
    p_tenant_id VARCHAR(50),
    p_record_id UUID,
    p_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    id UUID,
    action VARCHAR(20),
    user_id UUID,
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],
    created_at TIMESTAMP WITH TIME ZONE,
    ip_address INET
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id,
        a.action,
        a.user_id,
        a.old_values,
        a.new_values,
        a.changed_fields,
        a.created_at,
        a.ip_address
    FROM sys_audit_log a
    WHERE a.tenant_id = p_tenant_id
      AND a.record_id = p_record_id
    ORDER BY a.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_record_audit_trail IS 'Get complete audit history for a single record';


-- Get user activity summary
CREATE OR REPLACE FUNCTION get_user_activity_summary(
    p_tenant_id VARCHAR(50),
    p_user_id UUID,
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE (
    action VARCHAR(20),
    object_name VARCHAR(100),
    operation_count BIGINT,
    success_count BIGINT,
    failed_count BIGINT,
    total_affected INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.action,
        a.object_name,
        COUNT(*) as operation_count,
        COUNT(*) FILTER (WHERE a.status = 'success') as success_count,
        COUNT(*) FILTER (WHERE a.status = 'failed') as failed_count,
        SUM(a.affected_count)::INTEGER as total_affected
    FROM sys_audit_log a
    WHERE a.tenant_id = p_tenant_id
      AND a.user_id = p_user_id
      AND a.created_at >= CURRENT_TIMESTAMP - INTERVAL '1 day' * p_days
    GROUP BY a.action, a.object_name
    ORDER BY operation_count DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_user_activity_summary IS 'Get summary of user activity over time period';


-- ============================================================================
-- Default Retention Policies
-- ============================================================================

-- Insert default retention policy (1 year for all tenants)
-- This will be executed when a new tenant is provisioned
-- INSERT INTO sys_audit_retention_policy (tenant_id, object_name, retention_days)
-- VALUES ('tenant_id_here', NULL, 365)
-- ON CONFLICT (tenant_id, object_name) DO NOTHING;
