# Appify OM Service - AWS Deployment Guide

## Pre-Deployment Checklist

### 1. AWS Resources Required

Before deploying, ensure these AWS resources exist:

- [ ] **ECS Cluster**: `appify` (should already exist)
- [ ] **ECR Repository**: `appify-om` (create if needed)
- [ ] **CloudWatch Log Group**: `/ecs/appify-om` (create if needed)
- [ ] **Service Discovery Namespace**: `appify.local` (should already exist)
- [ ] **VPC and Subnets**: Private subnets for ECS tasks
- [ ] **Security Groups**: Allow traffic between services

### 2. Create Missing AWS Resources

#### Create ECR Repository

```bash
aws ecr create-repository \
  --repository-name appify-om \
  --profile appify-unshackle \
  --region us-west-1
```

#### Create CloudWatch Log Group

```bash
aws logs create-log-group \
  --log-group-name /ecs/appify-om \
  --profile appify-unshackle \
  --region us-west-1
```

#### Get Existing Resources Info

```bash
# Get VPC ID
aws ec2 describe-vpcs \
  --profile appify-unshackle \
  --region us-west-1 \
  --filters "Name=tag:Name,Values=appify-vpc" \
  --query 'Vpcs[0].VpcId' \
  --output text

# Get Private Subnet IDs
aws ec2 describe-subnets \
  --profile appify-unshackle \
  --region us-west-1 \
  --filters "Name=tag:Name,Values=appify-private-*" \
  --query 'Subnets[*].SubnetId' \
  --output text

# Get Security Group ID
aws ec2 describe-security-groups \
  --profile appify-unshackle \
  --region us-west-1 \
  --filters "Name=tag:Name,Values=appify-ecs-sg" \
  --query 'SecurityGroups[0].GroupId' \
  --output text

# Get Service Discovery Namespace ID
aws servicediscovery list-namespaces \
  --profile appify-unshackle \
  --region us-west-1 \
  --filters "Name=TYPE,Values=DNS_PRIVATE" \
  --query 'Namespaces[?Name==`appify.local`].Id' \
  --output text
```

---

## Deployment Steps

### Step 1: Create IAM Task Role

```bash
cd /Users/rangavaithyalingam/Projects/appify-om
./create-iam-task-role.sh
```

**What it does:**
- Creates `appify-om-task-role` IAM role
- Creates policy for Secrets Manager access
- Grants permission to read `appify/unshackle/identity/db` secret

**Verify:**
```bash
aws iam get-role \
  --role-name appify-om-task-role \
  --profile appify-unshackle \
  --region us-west-1
```

---

### Step 2: Create Service Discovery Entry

Create a service discovery entry so `om.appify.local` resolves to the OM service.

**First, get the namespace ID:**
```bash
NAMESPACE_ID=$(aws servicediscovery list-namespaces \
  --profile appify-unshackle \
  --region us-west-1 \
  --filters "Name=TYPE,Values=DNS_PRIVATE" \
  --query 'Namespaces[?Name==`appify.local`].Id' \
  --output text)

echo "Namespace ID: $NAMESPACE_ID"
```

**Create the service:**
```bash
aws servicediscovery create-service \
  --name om \
  --namespace-id $NAMESPACE_ID \
  --dns-config "DnsRecords=[{Type=A,TTL=10}]" \
  --health-check-custom-config "FailureThreshold=1" \
  --profile appify-unshackle \
  --region us-west-1
```

**Save the Service Registry ARN:**
```bash
SERVICE_ARN=$(aws servicediscovery list-services \
  --profile appify-unshackle \
  --region us-west-1 \
  --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
  --query 'Services[?Name==`om`].Arn' \
  --output text)

echo "Service Registry ARN: $SERVICE_ARN"
```

---

### Step 3: Create ECS Service (First Time Only)

**Get required IDs first:**

```bash
# Get subnet IDs (you'll need these)
SUBNET_IDS=$(aws ec2 describe-subnets \
  --profile appify-unshackle \
  --region us-west-1 \
  --filters "Name=tag:Name,Values=appify-private-*" \
  --query 'Subnets[*].SubnetId' \
  --output text | tr '\t' ',')

echo "Subnets: $SUBNET_IDS"

# Get security group ID
SG_ID=$(aws ec2 describe-security-groups \
  --profile appify-unshackle \
  --region us-west-1 \
  --filters "Name=tag:Name,Values=appify-ecs-sg" \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

echo "Security Group: $SG_ID"
```

**Create the ECS service:**

```bash
aws ecs create-service \
  --cluster appify \
  --service-name appify-om \
  --task-definition appify-om:1 \
  --desired-count 1 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_IDS],securityGroups=[$SG_ID],assignPublicIp=DISABLED}" \
  --service-registries "registryArn=$SERVICE_ARN" \
  --profile appify-unshackle \
  --region us-west-1
```

**Note:** This is only needed the FIRST time. After that, use `./deploy.sh` which will update the existing service.

---

### Step 4: Deploy the Service

```bash
cd /Users/rangavaithyalingam/Projects/appify-om
./deploy.sh
```

**What it does:**
1. Authenticates to ECR
2. Builds Docker image (linux/amd64 platform)
3. Tags image with timestamp and `latest`
4. Pushes to ECR
5. Registers new task definition
6. Updates ECS service with force new deployment

**Monitor deployment:**
```bash
# Watch service status
aws ecs describe-services \
  --cluster appify \
  --services appify-om \
  --profile appify-unshackle \
  --region us-west-1 \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Events:events[0:3]}' \
  --output json

# Watch task status
aws ecs list-tasks \
  --cluster appify \
  --service-name appify-om \
  --profile appify-unshackle \
  --region us-west-1

# View logs
aws logs tail /ecs/appify-om --follow --profile appify-unshackle --region us-west-1
```

---

## Verification

### 1. Check Service is Running

```bash
aws ecs describe-services \
  --cluster appify \
  --services appify-om \
  --profile appify-unshackle \
  --region us-west-1 \
  --query 'services[0].{Status:status,DesiredCount:desiredCount,RunningCount:runningCount}'
```

**Expected:**
```json
{
  "Status": "ACTIVE",
  "DesiredCount": 1,
  "RunningCount": 1
}
```

### 2. Check DNS Resolution

From within your VPC (e.g., via EC2 instance or bastion):

```bash
nslookup om.appify.local
```

**Expected:** Should resolve to private IP(s) of the OM containers

### 3. Test Health Endpoint

From an EC2 instance in the same VPC:

```bash
curl http://om.appify.local:8000/health
```

**Expected:**
```json
{
  "status": "healthy",
  "service": "appify-om",
  "version": "0.1.0",
  "environment": "production"
}
```

### 4. Check CloudWatch Logs

```bash
aws logs tail /ecs/appify-om --since 5m --profile appify-unshackle --region us-west-1
```

**Look for:**
- Startup logs showing service initialization
- No errors about missing secrets or database connections
- Health check passing

---

## Troubleshooting

### Issue: Service won't start (task keeps stopping)

**Check task logs:**
```bash
# Get the latest stopped task
TASK_ARN=$(aws ecs list-tasks \
  --cluster appify \
  --service-name appify-om \
  --desired-status STOPPED \
  --profile appify-unshackle \
  --region us-west-1 \
  --query 'taskArns[0]' \
  --output text)

# Get stop reason
aws ecs describe-tasks \
  --cluster appify \
  --tasks $TASK_ARN \
  --profile appify-unshackle \
  --region us-west-1 \
  --query 'tasks[0].{StopCode:stopCode,StopReason:stoppedReason,Containers:containers[*].{Name:name,Reason:reason}}'
```

**Common causes:**
- IAM role doesn't have Secrets Manager permissions
- Secret `appify/unshackle/identity/db` doesn't exist
- Image failed to pull from ECR
- Health check failing

### Issue: Can't connect to database

**Check:**
1. Security group allows traffic from OM to RDS
2. Secret exists and has correct structure:
   ```bash
   aws secretsmanager get-secret-value \
     --secret-id appify/unshackle/identity/db \
     --profile appify-unshackle \
     --region us-west-1 \
     --query SecretString \
     --output text | jq
   ```
3. Database `tenants` exists

### Issue: Service Discovery not working

**Verify registration:**
```bash
aws servicediscovery discover-instances \
  --namespace-name appify.local \
  --service-name om \
  --profile appify-unshackle \
  --region us-west-1
```

**Expected:** Should return at least one healthy instance

---

## Post-Deployment

### Update Identity Service Configuration

The identity service needs to know the OM service URL.

**Update identity service environment:**
```bash
# This is done in Step 7 - wait for user approval
```

---

## Rollback

If deployment fails and you need to rollback:

```bash
# Revert to previous task definition revision
aws ecs update-service \
  --cluster appify \
  --service appify-om \
  --task-definition appify-om:PREVIOUS_REVISION \
  --force-new-deployment \
  --profile appify-unshackle \
  --region us-west-1
```

---

## Cleanup (If Needed)

To remove the service:

```bash
# Scale to 0
aws ecs update-service \
  --cluster appify \
  --service appify-om \
  --desired-count 0 \
  --profile appify-unshackle \
  --region us-west-1

# Delete service
aws ecs delete-service \
  --cluster appify \
  --service appify-om \
  --force \
  --profile appify-unshackle \
  --region us-west-1

# Delete service discovery entry
aws servicediscovery delete-service \
  --id SERVICE_ID \
  --profile appify-unshackle \
  --region us-west-1
```
