-- Migration: Add s3_folder_path to sys_object_metadata
-- Run this on EXISTING tenant schemas and core schema
-- For new tenants, this is already in tenant-base-schema.sql

-- Add s3_folder_path column
ALTER TABLE sys_object_metadata 
ADD COLUMN IF NOT EXISTS s3_folder_path TEXT;

-- Add comment
COMMENT ON COLUMN sys_object_metadata.s3_folder_path IS 'S3 folder path for storing files related to this object (e.g., s3://unshackle-appify/<tenant_uuid>/<object_uuid>/)';

-- Verify column added
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns
WHERE table_name = 'sys_object_metadata' 
  AND column_name = 's3_folder_path';
