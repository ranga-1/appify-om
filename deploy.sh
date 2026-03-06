#!/bin/bash

set -e

# ============================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================
AWS_REGION="us-west-1"
AWS_ACCOUNT_ID="643942183493"
ECR_REPO="appify-om"
ECS_CLUSTER="appify"
ECS_SERVICE="appify-om"
TASK_FAMILY="appify-om"
# ============================================

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Appify Object Modeler Service Deployment ===${NC}"
echo ""

# Step 1: Authenticate Docker to ECR
echo -e "${GREEN}Step 1: Authenticating to ECR...${NC}"
aws ecr get-login-password --profile appify-unshackle --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Step 2: Build Docker image for linux/amd64
echo -e "${GREEN}Step 2: Building Docker image for linux/amd64...${NC}"
docker build --platform linux/amd64 -t $ECR_REPO:latest .

# Step 3: Tag the image
echo -e "${GREEN}Step 3: Tagging image...${NC}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
docker tag $ECR_REPO:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest
docker tag $ECR_REPO:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$TIMESTAMP

# Step 4: Push to ECR
echo -e "${GREEN}Step 4: Pushing to ECR...${NC}"
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$TIMESTAMP

# Step 5: Register new task definition
echo -e "${GREEN}Step 5: Registering task definition...${NC}"
TASK_REVISION=$(aws ecs register-task-definition \
  --profile appify-unshackle \
  --cli-input-json file://task-definition.json \
  --region $AWS_REGION \
  --query 'taskDefinition.revision' \
  --output text)

echo -e "${GREEN}Registered task definition revision: $TASK_REVISION${NC}"

# Step 6: Update ECS service
echo -e "${GREEN}Step 6: Updating ECS service...${NC}"
aws ecs update-service \
  --profile appify-unshackle \
  --cluster $ECS_CLUSTER \
  --service $ECS_SERVICE \
  --task-definition $TASK_FAMILY:$TASK_REVISION \
  --force-new-deployment \
  --region $AWS_REGION

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo -e "Service: ${YELLOW}$ECS_SERVICE${NC}"
echo -e "Cluster: ${YELLOW}$ECS_CLUSTER${NC}"
echo -e "Task Definition: ${YELLOW}$TASK_FAMILY:$TASK_REVISION${NC}"
echo ""
echo -e "${YELLOW}Monitor deployment:${NC}"
echo "aws ecs describe-services --profile appify-unshackle --cluster $ECS_CLUSTER --services $ECS_SERVICE --region $AWS_REGION"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo "aws logs tail /ecs/appify-om --follow --profile appify-unshackle --region $AWS_REGION"
