CREATE TABLE IF NOT EXISTS sys_object_metadata
(
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    label text NOT NULL,
    api_name text NOT NULL,
    description text,
    used_in_global_search boolean NOT NULL DEFAULT false,
    enable_audit boolean NOT NULL DEFAULT false,
    is_remote_object boolean NOT NULL DEFAULT false,
    fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    dependencies jsonb,
    uniqueness jsonb,
    reference_controls jsonb,
    advanced_search jsonb,
    validation_rules jsonb,
    status text NOT NULL DEFAULT 'draft',
    deployment_started_date timestamp with time zone,
    table_created_date timestamp with time zone,
    table_name text,
    deployment_error text,
    s3_folder_path text,
    created_by uuid NOT NULL,
    created_date timestamp with time zone NOT NULL DEFAULT now(),
    modified_by uuid NOT NULL,
    modified_date timestamp with time zone NOT NULL DEFAULT now(),
    audit_info jsonb,
    CONSTRAINT object_metadata_pkey PRIMARY KEY (id),
    CONSTRAINT object_metadata_api_name_key UNIQUE (api_name),
    CONSTRAINT object_metadata_label_key UNIQUE (label),
    CONSTRAINT valid_api_name CHECK (api_name ~ '^[a-z][a-z0-9_]*$'::text),
    CONSTRAINT valid_status CHECK (status IN ('draft', 'deploying', 'created', 'modified', 'failed')),
    CONSTRAINT valid_fields CHECK (jsonb_typeof(fields) = 'array'::text),
    CONSTRAINT valid_dependencies CHECK (dependencies IS NULL OR jsonb_typeof(dependencies) = 'array'::text),
    CONSTRAINT valid_uniqueness CHECK (uniqueness IS NULL OR jsonb_typeof(uniqueness) = 'array'::text),
    CONSTRAINT valid_reference_controls CHECK (reference_controls IS NULL OR jsonb_typeof(reference_controls) = 'array'::text),
    CONSTRAINT valid_advanced_search CHECK (advanced_search IS NULL OR jsonb_typeof(advanced_search) = 'object'::text),
    CONSTRAINT valid_validation_rules CHECK (validation_rules IS NULL OR jsonb_typeof(validation_rules) = 'array'::text),
    CONSTRAINT valid_audit_info CHECK (audit_info IS NULL OR jsonb_typeof(audit_info) = 'object'::text)
);
CREATE INDEX IF NOT EXISTS idx_object_metadata_api_name ON sys_object_metadata USING btree (api_name);
CREATE INDEX IF NOT EXISTS idx_object_metadata_label ON sys_object_metadata USING btree (label);
CREATE INDEX IF NOT EXISTS idx_object_metadata_status ON sys_object_metadata USING btree (status);
CREATE INDEX IF NOT EXISTS idx_object_metadata_created_date ON sys_object_metadata USING btree (created_date DESC);
CREATE INDEX IF NOT EXISTS idx_object_metadata_modified_date ON sys_object_metadata USING btree (modified_date DESC);
CREATE INDEX IF NOT EXISTS idx_object_metadata_table_created_date ON sys_object_metadata USING btree (table_created_date);
CREATE INDEX IF NOT EXISTS idx_object_metadata_global_search ON sys_object_metadata USING btree (used_in_global_search) WHERE used_in_global_search = true;
CREATE INDEX IF NOT EXISTS idx_object_metadata_failed_deployment ON sys_object_metadata USING btree (status) WHERE status = 'failed';
CREATE INDEX IF NOT EXISTS idx_object_metadata_deploying ON sys_object_metadata USING btree (status) WHERE status = 'deploying';
CREATE INDEX IF NOT EXISTS idx_object_metadata_modified ON sys_object_metadata USING btree (status) WHERE status = 'modified';
CREATE INDEX IF NOT EXISTS idx_object_metadata_fields ON sys_object_metadata USING gin (fields);
CREATE INDEX IF NOT EXISTS idx_object_metadata_dependencies ON sys_object_metadata USING gin (dependencies);
CREATE INDEX IF NOT EXISTS idx_object_metadata_validation_rules ON sys_object_metadata USING gin (validation_rules);
CREATE INDEX IF NOT EXISTS idx_object_metadata_audit_info ON sys_object_metadata USING gin (audit_info);
CREATE TRIGGER trg_object_metadata_modified_date
    BEFORE UPDATE ON sys_object_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_object_metadata_modified_date();
CREATE TABLE IF NOT EXISTS sys_om_datatype_mappings
(
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    db_datatype text NOT NULL,
    om_datatype text NOT NULL,
    properties jsonb NOT NULL,
    notes text,
    created_by uuid NOT NULL,
    created_date timestamp with time zone NOT NULL DEFAULT now(),
    modified_by uuid NOT NULL,
    modified_date timestamp with time zone NOT NULL DEFAULT now(),
    additional_audit_info jsonb,
    CONSTRAINT om_datatype_mappings_pkey PRIMARY KEY (id),
    CONSTRAINT om_datatype_mappings_om_datatype_key UNIQUE (om_datatype),
    CONSTRAINT valid_properties CHECK (jsonb_typeof(properties) = 'object'::text),
    CONSTRAINT valid_audit_info CHECK (additional_audit_info IS NULL OR jsonb_typeof(additional_audit_info) = 'object'::text)
);
CREATE INDEX IF NOT EXISTS idx_om_datatype_mappings_db_datatype ON sys_om_datatype_mappings USING btree (db_datatype);
CREATE INDEX IF NOT EXISTS idx_om_datatype_mappings_om_datatype ON sys_om_datatype_mappings USING btree (om_datatype);
CREATE INDEX IF NOT EXISTS idx_om_datatype_mappings_created_date ON sys_om_datatype_mappings USING btree (created_date);
CREATE INDEX IF NOT EXISTS idx_om_datatype_mappings_modified_date ON sys_om_datatype_mappings USING btree (modified_date);
CREATE INDEX IF NOT EXISTS idx_om_datatype_mappings_properties ON sys_om_datatype_mappings USING gin (properties);
CREATE INDEX IF NOT EXISTS idx_om_datatype_mappings_audit_info ON sys_om_datatype_mappings USING gin (additional_audit_info);
CREATE TRIGGER trg_update_modified_date
    BEFORE UPDATE ON sys_om_datatype_mappings
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_date();


-- Populate datatype mappings
-- System UUID for created_by/modified_by (00000000-0000-0000-0000-000000000000 = SYSTEM)
INSERT INTO sys_om_datatype_mappings (db_datatype, om_datatype, properties, notes, created_by, modified_by)
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


CREATE TABLE IF NOT EXISTS sys_users
(
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    email text NOT NULL,
    username text NOT NULL,
    first_name text,
    last_name text,
    full_name text,
    phone text,
    profile_picture_url text,
    is_active boolean NOT NULL DEFAULT true,
    is_email_verified boolean NOT NULL DEFAULT false,
    last_login_date timestamp with time zone,
    preferences jsonb DEFAULT '{}'::jsonb,
    metadata jsonb,
    created_by uuid NOT NULL,
    created_date timestamp with time zone NOT NULL DEFAULT now(),
    modified_by uuid NOT NULL,
    modified_date timestamp with time zone NOT NULL DEFAULT now(),
    audit_info jsonb,
    CONSTRAINT sys_users_pkey PRIMARY KEY (id),
    CONSTRAINT sys_users_user_id_key UNIQUE (user_id),
    CONSTRAINT sys_users_email_key UNIQUE (email),
    CONSTRAINT sys_users_username_key UNIQUE (username),
    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text),
    CONSTRAINT valid_phone CHECK (phone IS NULL OR phone ~ '^\+?[1-9]\d{1,14}$'::text),
    CONSTRAINT valid_preferences CHECK (preferences IS NULL OR jsonb_typeof(preferences) = 'object'::text),
    CONSTRAINT valid_metadata CHECK (metadata IS NULL OR jsonb_typeof(metadata) = 'object'::text),
    CONSTRAINT valid_audit_info CHECK (audit_info IS NULL OR jsonb_typeof(audit_info) = 'object'::text)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_users_user_id ON sys_users USING btree (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_users_email ON sys_users USING btree (email);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_users_username ON sys_users USING btree (username);
CREATE INDEX IF NOT EXISTS idx_sys_users_is_active ON sys_users USING btree (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sys_users_full_name ON sys_users USING btree (full_name);
CREATE INDEX IF NOT EXISTS idx_sys_users_last_login_date ON sys_users USING btree (last_login_date DESC);
CREATE INDEX IF NOT EXISTS idx_sys_users_created_date ON sys_users USING btree (created_date DESC);
CREATE INDEX IF NOT EXISTS idx_sys_users_modified_date ON sys_users USING btree (modified_date DESC);
CREATE INDEX IF NOT EXISTS idx_sys_users_preferences ON sys_users USING gin (preferences);
CREATE INDEX IF NOT EXISTS idx_sys_users_metadata ON sys_users USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_sys_users_audit_info ON sys_users USING gin (audit_info);
CREATE TRIGGER trg_sys_users_modified_date
    BEFORE UPDATE ON sys_users
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_date();