-- Populate datatype mappings in unshackle_core.public schema
-- This script should be run once on the core database to populate the sys_om_datatype_mappings table
-- for appify-admin users

-- Connect to unshackle_core database first, then run this script

-- Populate datatype mappings
-- System UUID for created_by/modified_by (00000000-0000-0000-0000-000000000000 = SYSTEM)
INSERT INTO public.sys_om_datatype_mappings (db_datatype, om_datatype, properties, notes, created_by, modified_by)
VALUES
    ('BOOLEAN', 'Boolean', '{"supports_default": true}'::jsonb, 'Boolean true/false values', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('NUMERIC', 'Currency', '{"requires_decimal_points": true, "supports_default": true}'::jsonb, 'Currency values with decimal precision', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('NUMERIC', 'Number', '{"requires_decimal_points": true, "supports_default": true}'::jsonb, 'Numeric values with decimal precision', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('DATE', 'Date', '{"supports_default": true, "supports_today_offset": true}'::jsonb, 'Date without time', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('TIMESTAMP WITH TIME ZONE', 'Datetime', '{"supports_default": true, "supports_today_offset": true}'::jsonb, 'Date and time with timezone', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('CITEXT', 'Email', '{"supports_unique": true}'::jsonb, 'Case-insensitive email addresses', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('VARCHAR', 'Phone', '{"max_length": 20, "format": "E.164"}'::jsonb, 'Phone numbers in E.164 format', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('VARCHAR', 'Text', '{"requires_length": true, "default_length": 255}'::jsonb, 'Short text with max length', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('TEXT', 'LongText', '{}'::jsonb, 'Long text without length limit', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('TEXT[]', 'Picklist', '{"requires_values": true}'::jsonb, 'Array of predefined values', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('TEXT', 'Picture', '{"stores": "S3_URL"}'::jsonb, 'S3 URL for picture storage', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('TEXT', 'Video', '{"stores": "S3_URL"}'::jsonb, 'S3 URL for video storage', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('UUID', 'Reference', '{"requires_referenced_object": true, "on_delete": "RESTRICT"}'::jsonb, 'Foreign key reference to another object', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000'),
    ('TEXT', 'URL', '{"format": "URL"}'::jsonb, 'Web URLs', '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000')
ON CONFLICT (om_datatype) DO NOTHING;

-- Verify insertion
SELECT COUNT(*) as datatype_count FROM public.sys_om_datatype_mappings;
SELECT om_datatype, db_datatype FROM public.sys_om_datatype_mappings ORDER BY om_datatype;
