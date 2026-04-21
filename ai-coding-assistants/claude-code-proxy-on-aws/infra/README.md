# Infrastructure (AWS CDK)

The CDK app consists of 2 stacks (`FoundationStack`, `ServiceStack`) and supporting constructs. Refer to this guide when using the CDK CLI directly instead of the deployment script (`scripts/deploy.sh`).

## Prerequisites

- Python 3.13 + [uv](https://docs.astral.sh/uv/)
- Node.js + CDK CLI (`npm install -g aws-cdk`)
- AWS credentials configured
- Docker running (for container image builds)

## Install Dependencies

```bash
# From the project root
uv sync --group dev --group infra
```

## CDK Bootstrap (First Time Only)

```bash
cd infra
cdk bootstrap
```

## Synth (Template Generation Only)

```bash
cd infra

# With HTTPS (ACM certificate required)
cdk synth \
  -c identity_store_id=d-1234567890 \
  -c acm_certificate_arn=<YOUR_ACM_CERTIFICATE_ARN>

# Without HTTPS (HTTP only)
cdk synth -c identity_store_id=d-1234567890
```

## Deploy

```bash
cd infra

# List stacks
cdk list

# Review changes
cdk diff

# Deploy all stacks
cdk deploy --all \
  -c identity_store_id=d-1234567890 \
  --require-approval broadening

# Deploy with ACM certificate
cdk deploy --all \
  -c identity_store_id=d-1234567890 \
  -c acm_certificate_arn=<YOUR_ACM_CERTIFICATE_ARN> \
  --require-approval broadening
```

## Environment-Specific Deployment

Override `cdk.json` context to deploy to a different environment:

```bash
cdk deploy --all \
  -c environment=prod \
  -c region=ap-northeast-2 \
  -c identity_store_id=d-1234567890
```

Settings automatically applied when `environment=prod`:
- Log retention: 1 week → 1 month
- Aurora deletion protection enabled
- Snapshot-based deletion policy

## Stack Structure

```
FoundationStack    VPC, Subnets, SGs, VPC Endpoints, Aurora, KMS, Secrets Manager
    |
    +-- ServiceStack       AMP, ECS Cluster, ECR, ALB, API Gateway
            |
            +-- ApiConstruct            API Gateway `/v1/auth/token`, `/v1/admin/*`
            +-- GatewayTaskDefinition   ECS migrate/gateway-app/adot containers
```

Runtime endpoints (`/v1/healthz`, `/v1/models`, `/v1/messages`) go directly to the public ALB without passing through API Gateway.

## Key Configuration Values (cdk.json)

| Key | Default | Description |
|-----|---------|-------------|
| `environment` | `dev` | Deployment environment |
| `region` | `ap-northeast-2` | AWS region |
| `app_name` | `claude-proxy` | Resource name prefix |
| `identity_store_id` | _(required)_ | IAM Identity Center identity store ID |
| `vpc_cidr` | `10.0.0.0/16` | VPC CIDR |
| `aurora_min_capacity` | `0.5` | Aurora Serverless minimum ACU |
| `aurora_max_capacity` | `1.0` | Aurora Serverless maximum ACU |
| `acm_certificate_arn` | _(none)_ | ACM certificate ARN (HTTP only if not provided) |
