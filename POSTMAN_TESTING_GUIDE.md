# Testing the Appify Object Modeler API with Postman

## Setup

### 1. Import the Collection
1. Open Postman
2. Click **Import** in the top-left
3. Select `Appify_OM_API.postman_collection.json`
4. The collection will appear in your Collections sidebar

### 2. Import the Environment
1. Click **Import** again
2. Select `Appify_OM_Local.postman_environment.json` for local testing
3. Or select `Appify_OM_Production.postman_environment.json` for production
4. Select the environment from the dropdown in the top-right

### 3. Configure Environment Variables
In the environment settings, update these values:

**Local Environment:**
- `base_url`: `http://localhost:8000` (default)
- `user_id`: Your test user UUID
- `tenant_id`: Your test tenant schema name (e.g., "acme")
- `object_name`: The object you're testing (e.g., "employee")
- `record_id`: Leave empty initially - will be set after creating records

**Production Environment:**
- `base_url`: Your production API URL
- `user_id`: Production user UUID
- `tenant_id`: Production tenant name
- `object_name`: Object name
- `record_id`: Leave empty initially

## Testing Workflow

### Phase 1: Health Check
1. **Health** - Verify API is running
2. **API Info** - Get API version and info

### Phase 2: Basic CRUD Operations
1. **Create Record** - Creates a new record, returns `record_id`
   - Copy the returned `id` to your environment's `record_id` variable
2. **Get Record by ID** - Retrieves the created record
3. **Update Record** - Modifies the record
4. **Query Records** - Search with filters
5. **Delete Record** - Removes the record

### Phase 3: Advanced Operations

#### Bulk Operations
1. **Bulk Create** - Create multiple records at once (max 1000)
2. **Bulk Update** - Update multiple records matching filters
3. **Bulk Delete** - Delete multiple records matching filters

#### Aggregations
1. **Count Records** - Count with filters
2. **Average Salary by Department** - Group by with aggregations
3. **Salary Stats** - Multiple aggregations (MIN, MAX, AVG, SUM)

#### Export/Import
1. **Export to CSV** - Download filtered data as CSV
2. **Export to JSON** - Download as JSON
3. **Export to Excel** - Download as Excel (requires `openpyxl`)
4. **Import from CSV** - Upload CSV data
5. **Import from JSON** - Upload JSON data

### Phase 4: Production Features

#### Audit Logging
1. **Get Record Audit History** - See all changes to a record
   - Shows create, update, delete operations
   - Displays old/new values, user, timestamp
   
2. **Get User Activity Summary** - View user's activity over time
   - Operation counts by action and object
   - Configurable time period (days parameter)

#### Soft Deletes
1. **Get Deleted Records** - List soft-deleted records for an object
   - Shows deletion timestamp, deleted by, reason
   - Days until permanent deletion
   
2. **Undelete Record** - Restore a soft-deleted record
   - Provide record_id and restoration reason
   - Record becomes active again

## Rate Limiting

The API enforces rate limits per operation type:
- **CRUD**: 1,000 requests/hour per user
- **Bulk**: 100 requests/hour per user
- **Export**: 10 requests/hour per user
- **Import**: 10 requests/hour per user
- **Query**: 500 requests/hour per user
- **Aggregate**: 200 requests/hour per user

Responses include rate limit headers:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1709855400
```

If you exceed limits, you'll receive HTTP 429 with `Retry-After` header.

## Example Test Flow

### Test Scenario: Employee Management

1. **Create Employee**
   ```json
   POST /api/v1/data/employee
   {
     "first_name": "John",
     "last_name": "Doe",
     "email": "john.doe@example.com",
     "department": "Engineering",
     "salary": 120000
   }
   ```
   → Copy returned `id` to `record_id` variable

2. **Get Employee**
   ```
   GET /api/v1/data/employee/{{record_id}}
   ```

3. **Update Salary**
   ```json
   PUT /api/v1/data/employee/{{record_id}}
   {
     "salary": 135000
   }
   ```

4. **Check Audit History**
   ```
   GET /api/v1/admin/audit/record/{{record_id}}
   ```
   → See create and update operations with old/new values

5. **Query High Earners**
   ```json
   POST /api/v1/data/employee/query
   {
     "filters": [
       {"field": "salary", "operator": ">=", "value": 130000}
     ],
     "order_by": ["salary DESC"]
   }
   ```

6. **Aggregate by Department**
   ```json
   POST /api/v1/data/employee/aggregate
   {
     "aggregations": [
       {"function": "AVG", "field": "salary", "alias": "avg_salary"},
       {"function": "COUNT", "field": "*", "alias": "count"}
     ],
     "group_by": ["department"]
   }
   ```

7. **Export to CSV**
   ```json
   POST /api/v1/data/employee/export
   {
     "format": "csv",
     "filters": [
       {"field": "department", "operator": "=", "value": "Engineering"}
     ]
   }
   ```

8. **Delete Employee**
   ```
   DELETE /api/v1/data/employee/{{record_id}}
   ```

9. **View Deleted Records**
   ```
   GET /api/v1/admin/deleted/employee
   ```

10. **Restore Employee**
    ```json
    POST /api/v1/admin/undelete
    {
      "object_name": "employee",
      "record_id": "{{record_id}}",
      "reason": "Accidental deletion"
    }
    ```

## Running Local Tests

Before testing, start the local API server:

```bash
cd /Users/rangavaithyalingam/Projects/appify-om
./run-local.sh
```

The API will be available at `http://localhost:8000`.

You can also run automated tests:

```bash
pytest tests/ -v
```

Expected: **161 tests passing** (63 Phase 1 + 11 Phase 2 + 40 Phase 3 + 47 Phase 4)

## Troubleshooting

### 401 Unauthorized
- Verify `X-User-ID` header is set correctly
- Check user has permissions for the operation

### 400 Bad Request
- Check request body matches expected schema
- Verify field names match your object schema

### 403 Forbidden
- User lacks permission for this operation
- Check role assignments in `sys_user_roles` table

### 404 Not Found
- Record doesn't exist
- Object name is incorrect
- Check `tenant_id` is correct

### 429 Too Many Requests
- You've exceeded rate limits
- Wait for `Retry-After` seconds
- Check `X-RateLimit-Reset` timestamp

### 500 Internal Server Error
- Check API logs for details
- Verify database connection
- Check Redis connection (for rate limiting)

## Advanced Testing

### Permission Testing
Test different user roles by changing the `user_id`:
1. Create users with different roles in your tenant
2. Update `user_id` environment variable
3. Test operations with restricted permissions

### Bulk Load Testing
Create test data:
```bash
# Generate 1000 employee records
# Use Bulk Create endpoint
# Test pagination with Query endpoint
```

### Performance Testing
Use Postman's Collection Runner:
1. Select the collection
2. Click **Run**
3. Set iterations and data file
4. Monitor response times

### Audit Trail Testing
1. Perform series of operations (create, update, delete)
2. Check audit history shows all operations
3. Verify old/new values are captured
4. Confirm user and timestamp are correct

## Documentation

For complete API documentation:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

## Support

For issues or questions:
1. Check [PHASE4_SUMMARY.md](PHASE4_SUMMARY.md) for feature details
2. Review test files in `tests/` for examples
3. Check API logs for error details
