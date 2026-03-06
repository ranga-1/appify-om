CREATE OR REPLACE FUNCTION update_modified_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.modified_date = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_object_metadata_modified_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.modified_date = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;