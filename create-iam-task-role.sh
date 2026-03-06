#!/bin/bash

# ============================================================================
# Create IAM Task Role for appify-om ECS Service
# ============================================================================
# This script creates an IAM role that allows the ECS task to:
# - Read secrets from AWS Secrets Manager (database credentials)
#
# Run: chmod +x create-iam-task-role.sh && ./create-iam-task-role.sh
# ============================================================================

set -e

AWS_PROFILE="appify-unshackle"
AWS_REGION="us-west-1"
ACCOUNT_ID="643942183493"

ROLE_NAME="appify-om-task-role"
POLICY_NAME="appify-om-secrets-access"

echo "======================================================================"
echo "Creating IAM Task Role for appify-om"
echo "======================================================================"
echo ""

# Step 1: Create trust policy document
echo "1. Creating trust policy for ECS tasks..."
TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
)

# Check if role already exists
ROLE_EXISTS=$(AWS_PROFILE=$AWS_PROFILE aws iam get-role \
    --role-name $ROLE_NAME \
    --region $AWS_REGION \
    2>/dev/null || echo "")

if [ -z "$ROLE_EXISTS" ]; then
    echo "Creating IAM role: $ROLE_NAME"
    AWS_PROFILE=$AWS_PROFILE aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document "$TRUST_POLICY" \
        --description "Task role for appify-om ECS service - allows access to Secrets Manager for database credentials" \
        --region $AWS_REGION
    echo "✅ IAM role created"
else
    echo "✅ IAM role already exists: $ROLE_NAME"
fi

echo ""

# Step 2: Create policy for Secrets Manager access
echo "2. Creating IAM policy for Secrets Manager access..."
POLICY_DOCUMENT=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-west-1:${ACCOUNT_ID}:secret:appify/unshackle/identity/db-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:ListSecrets"
      ],
      "Resource": "*"
    }
  ]
}
EOF
)

# Check if policy already exists
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"
POLICY_EXISTS=$(AWS_PROFILE=$AWS_PROFILE aws iam get-policy \
    --policy-arn $POLICY_ARN \
    --region $AWS_REGION \
    2>/dev/null || echo "")

if [ -z "$POLICY_EXISTS" ]; then
    echo "Creating IAM policy: $POLICY_NAME"
    AWS_PROFILE=$AWS_PROFILE aws iam create-policy \
        --policy-name $POLICY_NAME \
        --policy-document "$POLICY_DOCUMENT" \
        --description "Allows appify-om to read database credentials from Secrets Manager" \
        --region $AWS_REGION
    echo "✅ IAM policy created"
else
    echo "✅ IAM policy already exists: $POLICY_NAME"
fi

echo ""

# Step 3: Attach policy to role
echo "3. Attaching policy to role..."
AWS_PROFILE=$AWS_PROFILE aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn $POLICY_ARN \
    --region $AWS_REGION

echo "✅ Policy attached to role"

echo ""
echo "======================================================================"
echo "✅ IAM Task Role Setup Complete"
echo "======================================================================"
echo ""
echo "Role ARN: arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "Policy ARN: ${POLICY_ARN}"
echo ""
echo "Next steps:"
echo "1. Verify the role in IAM console"
echo "2. Use this role ARN in your task-definition.json"
echo "3. Deploy the service with: ./deploy.sh"
