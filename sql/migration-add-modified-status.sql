-- Migration: Add 'modified' status to sys_object_metadata
-- Date: 2026-03-09
-- Description: Updates the valid_status constraint to include 'modified' status
--              which indicates an object has been deployed and then modified,
--              requiring redeployment to sync changes.

-- This migration should be run on each tenant schema

-- Drop existing constraint
ALTER TABLE sys_object_metadata 
DROP CONSTRAINT IF EXISTS valid_status;

-- Add updated constraint with 'modified' status
ALTER TABLE sys_object_metadata 
ADD CONSTRAINT valid_status 
CHECK (status IN ('draft', 'deploying', 'created', 'modified', 'failed'));

-- Add index for 'modified' status queries (for performance)
CREATE INDEX IF NOT EXISTS idx_object_metadata_modified
ON sys_object_metadata USING btree (status) 
WHERE status = 'modified';

-- Optionally: Update any existing 'draft' status objects that have table_created_date
-- to 'modified' status (these were deployed objects that were changed)
-- Uncomment the following if you want to retroactively apply this logic:

-- UPDATE sys_object_metadata 
-- SET status = 'modified' 
-- WHERE status = 'draft' 
--   AND table_created_date IS NOT NULL;

-- Note: The above UPDATE is commented out to be conservative. 
-- Review your data before running it.
