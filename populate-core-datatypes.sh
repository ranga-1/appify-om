#!/bin/bash

# Script to populate datatype mappings in unshackle_core.public schema
# This is a ONE-TIME setup for the core schema used by appify-admin users

set -e

echo "=== Populating Core Schema Datatype Mappings ==="
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
echo "User: $DB_USER"
echo ""

# Execute the SQL file
echo "Executing SQL to populate datatype mappings..."
PGPASSWORD=$DB_PASS psql \
    -h $DB_HOST \
    -p $DB_PORT \
    -U $DB_USER \
    -d $DB_NAME \
    -f sql/populate-core-datatype-mappings.sql

echo ""
echo "=== Done ==="
