#!/bin/bash

# ============================================================================
# Get AWS Resource IDs for appify-om Deployment
# ============================================================================
# This script retrieves all the AWS resource IDs you'll need for deployment
# ============================================================================

set -e

AWS_PROFILE="appify-unshackle"
AWS_REGION="us-west-1"

echo "======================================================================"
echo "Fetching AWS Resource IDs for appify-om"
echo "======================================================================"
echo ""

# VPC
echo "📍 VPC:"
VPC_ID=$(aws ec2 describe-vpcs \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --query 'Vpcs[0].VpcId' \
  --output text 2>/dev/null || echo "Not found")
echo "   ID: $VPC_ID"
echo ""

# Subnets
echo "🌐 Private Subnets:"
SUBNETS=$(aws ec2 describe-subnets \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --filters "Name=tag:Name,Values=*private*" "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[*].[SubnetId,Tags[?Key==`Name`].Value|[0],AvailabilityZone]' \
  --output text 2>/dev/null || echo "Not found")
echo "$SUBNETS" | awk '{printf "   %s (%s) in %s\n", $1, $2, $3}'
SUBNET_IDS=$(echo "$SUBNETS" | awk '{printf "%s%s", (NR==1?"":","), $1}')
echo "   Comma-separated: $SUBNET_IDS"
echo ""

# Security Group
echo "🔒 Security Group:"
SG_ID=$(aws ec2 describe-security-groups \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=*ecs*" \
  --query 'SecurityGroups[0].[GroupId,GroupName]' \
  --output text 2>/dev/null || echo "Not found")
echo "   $SG_ID"
echo ""

# Service Discovery Namespace
echo "🔍 Service Discovery:"
NAMESPACE=$(aws servicediscovery list-namespaces \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --filters "Name=TYPE,Values=DNS_PRIVATE" \
  --query 'Namespaces[?Name==`appify.local`].[Id,Name]' \
  --output text 2>/dev/null || echo "Not found")
echo "   Namespace: $NAMESPACE"

NAMESPACE_ID=$(echo "$NAMESPACE" | awk '{print $1}')

# Check if om service exists
if [ -n "$NAMESPACE_ID" ] && [ "$NAMESPACE_ID" != "Not" ]; then
    OM_SERVICE=$(aws servicediscovery list-services \
      --profile $AWS_PROFILE \
      --region $AWS_REGION \
      --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
      --query 'Services[?Name==`om`].[Id,Arn]' \
      --output text 2>/dev/null || echo "")
    
    if [ -n "$OM_SERVICE" ]; then
        echo "   ✅ om.appify.local service exists"
        echo "   $(echo $OM_SERVICE | awk '{print $1}')"
    else
        echo "   ❌ om.appify.local service NOT created yet"
        echo "   Run the create command from DEPLOYMENT.md"
    fi
fi
echo ""

# ECS Cluster
echo "🚀 ECS Cluster:"
CLUSTER_STATUS=$(aws ecs describe-clusters \
  --clusters appify \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --query 'clusters[0].[status,runningTasksCount,pendingTasksCount]' \
  --output text 2>/dev/null || echo "Not found")
echo "   Status: $CLUSTER_STATUS"
echo ""

# ECR Repository
echo "📦 ECR Repository:"
ECR_REPO=$(aws ecr describe-repositories \
  --repository-names appify-om \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --query 'repositories[0].[repositoryUri,createdAt]' \
  --output text 2>/dev/null || echo "NOT CREATED - Run: aws ecr create-repository --repository-name appify-om --profile appify-unshackle --region us-west-1")
echo "   $ECR_REPO"
echo ""

# CloudWatch Log Group
echo "📝 CloudWatch Log Group:"
LOG_GROUP=$(aws logs describe-log-groups \
  --log-group-name-prefix /ecs/appify-om \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --query 'logGroups[0].logGroupName' \
  --output text 2>/dev/null || echo "NOT CREATED - Run: aws logs create-log-group --log-group-name /ecs/appify-om --profile appify-unshackle --region us-west-1")
echo "   $LOG_GROUP"
echo ""

# IAM Roles
echo "🔐 IAM Roles:"
EXEC_ROLE=$(aws iam get-role \
  --role-name appify-ecs-task-execution-role \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --query 'Role.Arn' \
  --output text 2>/dev/null || echo "NOT FOUND")
echo "   Execution: $EXEC_ROLE"

TASK_ROLE=$(aws iam get-role \
  --role-name appify-om-task-role \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --query 'Role.Arn' \
  --output text 2>/dev/null || echo "NOT CREATED - Run: ./create-iam-task-role.sh")
echo "   Task:      $TASK_ROLE"
echo ""

# ECS Service
echo "🎯 ECS Service:"
SERVICE_STATUS=$(aws ecs describe-services \
  --cluster appify \
  --services appify-om \
  --profile $AWS_PROFILE \
  --region $AWS_REGION \
  --query 'services[0].[status,desiredCount,runningCount]' \
  --output text 2>/dev/null || echo "NOT CREATED")
echo "   $SERVICE_STATUS"
echo ""

echo "======================================================================"
echo "Summary for ECS Service Creation"
echo "======================================================================"
echo ""
echo "Copy these values for creating the ECS service:"
echo ""
echo "SUBNET_IDS=\"$SUBNET_IDS\""
echo "SG_ID=\"$(echo $SG_ID | awk '{print $1}')\""
echo "NAMESPACE_ID=\"$NAMESPACE_ID\""
echo ""
