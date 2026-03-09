# Verification Checklist - Appify OM Revision 26

## Implementation Summary

### Completed Enhancements

#### 1. Object Metadata API Validations (NEW in Revision 26)
- ✅ **API Name Immutability**: Prevents api_name changes after creation
- ✅ **Change Detection**: Only updates database when actual changes detected
- ✅ **Auto-Draft Status**: Automatically sets status='draft' when deployed object is modified

#### 2. CREATE/UPDATE Deployment Mode (Revision 25)
- ✅ **Mode Detection**: Automatically detects CREATE vs UPDATE based on table existence
- ✅ **UPDATE Mode**: Adds new columns to existing tables via ALTER TABLE
- ✅ **is_deleted System Field**: Added to all tables for soft-delete support
- ✅ **Field Filtering**: Respects mark_as_deleted flag, excludes from deployment
- ✅ **S3 Folder Paths**: Auto-generates and stores S3 paths for file storage
- ✅ **Table Verification**: Confirms table exists before marking status='created'

#### 3. Postman Collections (NEW in Revision 26)
- ✅ Updated existing Appify API Collection with Object Modeler endpoints
- ✅ Added 6 new Object Metadata requests
- ✅ Added Tenants & Datatypes section
- ✅ Enhanced descriptions with Revision 26 features

---

## Verification Steps

### Phase 1: Database Migration (REQUIRED FIRST)

**Execute migration script on existing schemas:**

```bash
# Connect to RDS via bastion
cd /Users/rangavaithyalingam/Projects/appify-unshackle
./start-bastion-tunnel.sh

# In another terminal, run migration
psql -h localhost -p 5432 -U unshackle_core_app -d unshackle_core \
  -f /Users/rangavaithyalingam/Projects/appify-om/sql/migration-add-s3-folder-path.sql
```

**Verify migration results:**
- [ ] s3_folder_path column added to unshackle_core.public.sys_object_metadata
- [ ] s3_folder_path column added to all tenants.tenant_*.sys_object_metadata schemas
- [ ] No errors during migration

---

### Phase 2: Object Metadata API Validations

#### Test 1: API Name Immutability

**Scenario**: Try to change label in a way that would change api_name

**Steps**:
1. Create object with label "Customer Account" → api_name: "{prefix}_customer_account"
2. Try to update label to "Client Account" → should generate api_name: "{prefix}_client_account"

**Expected Behavior**:
- [ ] Update request returns 400 Bad Request
- [ ] Error message explains api_name immutability
- [ ] Error shows old vs new api_name values

**Postman Request**: "Object Modeler > Object Metadata > Update Object Metadata" with modified label

---

#### Test 2: Change Detection - No Changes

**Scenario**: Submit update request with same values

**Steps**:
1. Get existing object metadata
2. Submit PUT request with exact same field values
3. Check response and database

**Expected Behavior**:
- [ ] Response returns 200 OK with current object
- [ ] modified_date timestamp NOT updated in database
- [ ] Log shows: "No changes detected for object {id}"

**Postman Request**: "Object Modeler > Object Metadata > Update Object Metadata" with identical values

---

#### Test 3: Change Detection - Actual Changes

**Scenario**: Submit update with real changes

**Steps**:
1. Get existing object
2. Update description or add new field
3. Check response

**Expected Behavior**:
- [ ] Response returns 200 OK with updated object
- [ ] modified_date timestamp IS updated
- [ ] modified_by shows user ID
- [ ] Changes reflected in database

**Postman Request**: "Object Modeler > Object Metadata > Update Object Metadata" with modified description

---

#### Test 4: Auto-Draft Status on Modification

**Scenario**: Modify a deployed object (status='created')

**Steps**:
1. Deploy an object → status changes to 'created'
2. Verify table exists in database
3. Update object (add new field)
4. Check status

**Expected Behavior**:
- [ ] Object status automatically changes to 'draft'
- [ ] Log shows: "Object {id} status changed to 'draft' due to modifications"
- [ ] Must redeploy to apply changes to table
- [ ] deployment_error cleared (if previously failed)

**Postman Requests**: 
- "Object Modeler > Object Metadata > Deploy Object (CREATE Mode)"
- "Object Modeler > Object Metadata > Update Object Metadata" (add field)
- "Object Modeler > Object Metadata > Get Object Metadata by ID" (verify status='draft')

---

### Phase 3: CREATE/UPDATE Deployment Mode

#### Test 5: CREATE Mode - New Table

**Scenario**: Deploy brand new object

**Steps**:
1. Create object with fields array
2. Deploy object
3. Verify table creation

**Expected Behavior**:
- [ ] Status changes: draft → deploying → created
- [ ] Response includes:
  - deployment_mode: "create"
  - table_name: "{prefix}_{sanitized_label}"
  - s3_folder_path: "s3://unshackle-appify/{tenant_id}/{object_id}/"
  - columns_created: list of all columns
- [ ] Table exists in database
- [ ] System columns present: id, created_by, modified_by, created_date, modified_date, is_deleted, audit_info
- [ ] User fields present with prefix: {prefix}_{field_name}
- [ ] is_deleted column: BOOLEAN NOT NULL DEFAULT false
- [ ] table_created_date populated in metadata
- [ ] deployment_started_date populated

**SQL Verification**:
```sql
-- Check table exists
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'tenant_{customer_id}' 
AND table_name = '{api_name}';

-- Check columns
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'tenant_{customer_id}'
AND table_name = '{api_name}'
ORDER BY ordinal_position;

-- Check is_deleted column
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_schema = 'tenant_{customer_id}'
AND table_name = '{api_name}'
AND column_name = 'is_deleted';
```

**Postman Request**: "5. Deploy Object (CREATE)"

---

#### Test 6: UPDATE Mode - Add Columns

**Scenario**: Add new fields to already-deployed object

**Steps**:
1. Use object from Test 5 (already deployed)
2. Update object to add 2 new fields
3. Status should auto-change to 'draft'
4. Deploy again
5. Verify new columns added

**Expected Behavior**:
- [ ] Response includes:
  - deployment_mode: "update"
  - columns_added: ["prefix_new_field1", "prefix_new_field2"]
  - table_name: same as before
  - s3_folder_path: same as before
- [ ] New columns exist in database table
- [ ] Existing columns UNCHANGED (data preserved)
- [ ] System columns UNCHANGED
- [ ] table_created_date PRESERVED from original CREATE
- [ ] deployment_started_date UPDATED to new deployment time

**SQL Verification**:
```sql
-- Check new columns exist
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'tenant_{customer_id}'
AND table_name = '{api_name}'
AND column_name IN ('{prefix}_new_field1', '{prefix}_new_field2');

-- Verify system columns unchanged
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_schema = 'tenant_{customer_id}'
AND table_name = '{api_name}'
AND column_name IN ('id', 'created_by', 'is_deleted');
```

**Postman Request**: "6. Deploy Object (UPDATE)"

---

#### Test 7: Field Soft Delete (mark_as_deleted)

**Scenario**: Mark field as deleted, verify not deployed

**Steps**:
1. Update object, set mark_as_deleted=true on one field
2. Deploy object
3. Check if column exists

**Expected Behavior**:
- [ ] Field with mark_as_deleted=true NOT deployed
- [ ] If field was previously deployed, column REMAINS in table (preserved)
- [ ] If field is new, column NOT created
- [ ] deployment response does NOT include marked-as-deleted fields

**SQL Verification**:
```sql
-- Check if column exists (should exist if previously deployed)
SELECT column_name 
FROM information_schema.columns
WHERE table_schema = 'tenant_{customer_id}'
AND table_name = '{api_name}'
AND column_name = '{prefix}_{deleted_field_name}';
```

**Postman Request**: "Object Modeler > Object Metadata > Update Object Metadata" + "Deploy Object (UPDATE Mode)"

---

#### Test 8: is_deleted Column Auto-Addition

**Scenario**: Deploy to table that exists but lacks is_deleted column (migration scenario)

**Steps**:
1. Manually drop is_deleted column from a deployed table
2. Redeploy object (UPDATE mode)
3. Verify is_deleted column re-added

**Expected Behavior**:
- [ ] UPDATE mode detects missing is_deleted column
- [ ] Adds: ALTER TABLE ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT false
- [ ] Deployment completes successfully
- [ ] is_deleted column exists with correct definition

**SQL Verification**:
```sql
-- Manually drop column
ALTER TABLE tenant_{customer_id}.{api_name} DROP COLUMN is_deleted;

-- Then redeploy via Postman

-- Verify column re-added
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_schema = 'tenant_{customer_id}'
AND table_name = '{api_name}'
AND column_name = 'is_deleted';
```

**Postman Request**: "6. Deploy Object (UPDATE)"

---

#### Test 9: S3 Folder Path Generation

**Scenario**: Verify S3 folder paths are generated and stored

**Steps**:
1. Deploy new object
2. Check s3_folder_path in response
3. Verify stored in database

**Expected Behavior**:
- [ ] Response includes: s3_folder_path: "s3://unshackle-appify/{tenant_id}/{object_id}/"
- [ ] Path stored in sys_object_metadata.s3_folder_path column
- [ ] Path format: s3://unshackle-appify/{tenant_uuid}/{object_uuid}/
- [ ] Tenant ID matches actual tenant UUID from JWT token

**SQL Verification**:
```sql
SELECT id, api_name, s3_folder_path
FROM tenant_{customer_id}.sys_object_metadata
WHERE id = '{object_id}';
```

**Postman Request**: "Object Modeler > Object Metadata > Deploy Object (CREATE/UPDATE Mode)"

---

### Phase 4: Failed Deployment Recovery

#### Test 10: Retry Failed Deployment

**Scenario**: Fix and retry a failed deployment

**Steps**:
1. Deploy object with invalid reference (non-existent table)
2. Verify status='failed' and deployment_error populated
3. Fix the issue (remove bad reference)
4. Set status back to 'draft'
5. Redeploy

**Expected Behavior**:
- [ ] Initial deploy fails with status='failed'
- [ ] deployment_error contains error message
- [ ] After setting status='draft', can redeploy
- [ ] Successful redeploy clears deployment_error
- [ ] Status changes to 'created'
- [ ] Table exists in database

**Postman Requests**: 
- "Object Modeler > Object Metadata > Deploy Object (CREATE Mode)" (initial fail)
- "Object Modeler > Object Metadata > Retry Failed Deployment" (set to draft)
- "Object Modeler > Object Metadata > Deploy Object (CREATE Mode)" (retry)

---

### Phase 5: Postman Collection Testing

#### Test 11: Authentication Flow

**Steps**:
1. Import appify-identity/Appify_API_Collection.postman_collection.json
2. Import appify-identity/Appify_Production.postman_environment.json
3. Update environment variables (username, password, customer_id)
4. Run "Authentication > 1. Login (Get Tokens)"
5. Verify tokens saved

**Expected Behavior**:
- [ ] Login returns 200 OK
- [ ] Response contains access_token and refresh_token
- [ ] Tokens auto-saved to environment variables
- [ ] Console shows: "✓ Tokens saved to environment"

**Postman Request**: "Authentication > 1. Login (Get Tokens)"

---

#### Test 12: Complete Object Lifecycle

**Steps** (use Object Modeler folder):
1. Authentication > Login
2. Object Metadata > List Object Metadata
3. Object Metadata > Create Object Metadata (saves object_id to environment)
4. Object Metadata > Get Object Metadata by ID
5. Object Metadata > Deploy Object (CREATE Mode)
6. Object Metadata > Update Object Metadata (add field)
7. Object Metadata > Deploy Object (UPDATE Mode)

**Expected Behavior**:
- [ ] All requests return expected status codes
- [ ] object_id automatically used in subsequent requests
- [ ] Deployment modes switch correctly (create → update)
- [ ] Can see full object lifecycle in responses

**Postman Folder**: "Object Modeler > Object Metadata"

---

#### Test 13: Health Check

**Steps**:
1. Run health check request (no auth required)

**Expected Behavior**:
- [ ] Returns 200 OK
- [ ] Response: {"status": "healthy"}
- [ ] Works without authentication token

**Postman Request**: "Health Check"

---

## Post-Deployment Verification

### Service Health

```bash
# Check ECS service status
aws ecs describe-services \
  --profile appify-unshackle \
  --region us-west-1 \
  --cluster appify \
  --services appify-om \
  --query 'services[0].[taskDefinition,deployments[0].rolloutState,runningCount]' \
  --output table

# Check CloudWatch logs
aws logs tail /ecs/appify-om \
  --profile appify-unshackle \
  --region us-west-1 \
  --since 5m \
  --format short
```

**Expected**:
- [ ] rolloutState: COMPLETED
- [ ] runningCount: 1
- [ ] No ERROR logs
- [ ] Health checks passing (200 OK)

---

### Database State

```sql
-- Verify migration applied
SELECT column_name, data_type 
FROM information_schema.columns
WHERE table_name = 'sys_object_metadata'
AND column_name = 's3_folder_path';

-- Check deployed objects
SELECT api_name, status, table_name, s3_folder_path
FROM tenant_{customer_id}.sys_object_metadata
WHERE status = 'created'
ORDER BY created_date DESC;

-- Verify table has is_deleted column
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'tenant_{customer_id}'
AND column_name = 'is_deleted';
```

**Expected**:
- [ ] s3_folder_path column exists in all schemas
- [ ] Deployed objects have table_name and s3_folder_path populated
- [ ] All deployed tables have is_deleted column

---

## Common Issues & Troubleshooting

### API Name Immutability Error

**Symptom**: "Cannot change api_name" error when updating label

**Cause**: New label generates different api_name than existing

**Solution**: 
- Keep original label, or
- Use label that sanitizes to same api_name (e.g., "Customer Account" vs "Customer  Account")

---

### No Changes Detected

**Symptom**: Update returns 200 but modified_date unchanged

**Cause**: Submitted values identical to existing values

**Solution**: 
- This is expected behavior (change detection working)
- Make actual change to trigger update

---

### Auto-Draft Not Triggering

**Symptom**: Object status doesn't change to 'draft' after update

**Cause**: Object was not in 'created' status (may be 'draft' already)

**Solution**:
- Auto-draft only applies to objects with status='created'
- If status is 'draft' or 'failed', it remains unchanged

---

### UPDATE Mode Not Triggering

**Symptom**: Deployment always uses CREATE mode

**Cause**: Table doesn't exist in database

**Solution**:
- Verify table actually exists in correct schema
- Check schema name: tenant_{customer_id} vs public
- Run: `SELECT * FROM information_schema.tables WHERE table_name = '{api_name}'`

---

### Missing is_deleted Column

**Symptom**: Table exists but lacks is_deleted column

**Cause**: Table created with older revision

**Solution**:
- Redeploy object in UPDATE mode
- Service auto-adds is_deleted column

---

## Summary Metrics

**Code Changes**:
- 1 file modified: app/services/object_metadata_service.py
- ~80 lines of enhanced change detection logic
- 3 Postman files created

**Database Changes**:
- 1 migration script: sql/migration-add-s3-folder-path.sql
- 1 column added: s3_folder_path to sys_object_metadata

**API Enhancements**:
- API name immutability validation
- Change detection (no-op updates)
- Auto-draft status on modification
- Comprehensive Postman collection (13 requests)

**Testing Coverage**:
- 13 verification tests across 5 phases
- CREATE/UPDATE mode coverage
- Error handling and recovery
- Full object lifecycle testing

---

## Next Steps After Verification

1. **Production Testing**: Use Postman collection against production environment
2. **Performance Testing**: Test with large field arrays (50+ fields)
3. **Concurrent Updates**: Test simultaneous updates to same object
4. **Reference Integrity**: Test complex object graphs with multiple references
5. **Audit Trail**: Verify modified_by and modified_date tracking accuracy
6. **S3 Integration**: Implement actual S3 folder creation (currently just path generation)
7. **Tenant Isolation**: Verify cross-tenant data isolation in multi-tenant scenarios

---

Generated: March 9, 2026
Revision: 26 (pending deployment)
Previous Revision: 25 (deployed)
