#!/bin/bash

# Script to check what datatype mappings exist in unshackle_core.public schema

set -e

echo "=== Checking Core Schema Datatype Mappings ==="
echo ""

# Get database credentials from AWS Secrets Manager
echo "Fetching database credentials..."
DB_SECRET=$(aws secretsmanager get-secret-value \
    --profile appify-unshackle \
    --region us-west-1 \
    --secret-id appify/unshackle/core/db \
    --query 'SecretString' \
    --output text)

DB_HOST=$(echo $DB_SECRET | jq -r '.host')
DB_PORT=$(echo $DB_SECRET | jq -r '.port')
DB_NAME=$(echo $DB_SECRET | jq -r '.dbname')
DB_USER=$(echo $DB_SECRET | jq -r '.username')
DB_PASS=$(echo $DB_SECRET | jq -r '.password')

echo "Database: $DB_HOST:$DB_PORT/$DB_NAME"
echo "Schema: public"
echo ""

# Query the table
echo "=== Datatype Mappings in public.sys_om_datatype_mappings ==="
PGPASSWORD=$DB_PASS psql \
    -h $DB_HOST \
    -p $DB_PORT \
    -U $DB_USER \
    -d $DB_NAME \
    -c "SELECT om_datatype, db_datatype FROM public.sys_om_datatype_mappings ORDER BY om_datatype;"

echo ""
echo "=== Count ==="
PGPASSWORD=$DB_PASS psql \
    -h $DB_HOST \
    -p $DB_PORT \
    -U $DB_USER \
    -d $DB_NAME \
    -c "SELECT COUNT(*) as total FROM public.sys_om_datatype_mappings;"

echo ""
echo "=== Done ==="
