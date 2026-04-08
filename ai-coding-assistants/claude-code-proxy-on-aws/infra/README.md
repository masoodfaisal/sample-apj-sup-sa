# Infrastructure (AWS CDK)

현재 CDK 앱은 2개 스택(`FoundationStack`, `ServiceStack`)과 supporting constructs로 구성됩니다. 배포 스크립트(`scripts/deploy.sh`) 대신 CDK CLI를 직접 사용할 때 참고하세요.

## 사전 요구사항

- Python 3.13 + [uv](https://docs.astral.sh/uv/)
- Node.js + CDK CLI (`npm install -g aws-cdk`)
- AWS 자격증명 설정 완료
- Docker 실행 중 (컨테이너 이미지 빌드)

## 의존성 설치

```bash
# 프로젝트 루트에서
uv sync --group dev --group infra
```

## CDK 부트스트랩 (최초 1회)

```bash
cd infra
cdk bootstrap
```

## Synth (템플릿 생성만)

```bash
cd infra

# HTTPS 사용 시 (ACM 인증서 필요)
cdk synth \
  -c identity_store_id=d-1234567890 \
  -c acm_certificate_arn=<YOUR_ACM_CERTIFICATE_ARN>

# HTTPS 없이 (HTTP만)
cdk synth -c identity_store_id=d-1234567890
```

## 배포

```bash
cd infra

# 스택 목록 확인
cdk list

# 변경사항 확인
cdk diff

# 전체 배포
cdk deploy --all \
  -c identity_store_id=d-1234567890 \
  --require-approval broadening

# ACM 인증서 지정하여 배포
cdk deploy --all \
  -c identity_store_id=d-1234567890 \
  -c acm_certificate_arn=<YOUR_ACM_CERTIFICATE_ARN> \
  --require-approval broadening
```

## 환경별 배포

`cdk.json`의 context를 오버라이드하여 다른 환경에 배포할 수 있습니다:

```bash
cdk deploy --all \
  -c environment=prod \
  -c region=ap-northeast-2 \
  -c identity_store_id=d-1234567890
```

`environment=prod`일 때 자동으로 적용되는 설정:
- 로그 보존: 1주 → 1개월
- Aurora 삭제 보호 활성화
- 스냅샷 기반 삭제 정책

## 스택 구조

```
FoundationStack    VPC, 서브넷, SG, VPC Endpoints, Aurora, KMS, Secrets Manager
    |
    +-- ServiceStack       AMP, ECS Cluster, ECR, ALB, API Gateway
            |
            +-- ApiConstruct            API Gateway `/v1/auth/token`, `/v1/admin/*`
            +-- GatewayTaskDefinition   ECS migrate/gateway-app/adot containers
```

런타임 엔드포인트(`/v1/healthz`, `/v1/models`, `/v1/messages`)는 API Gateway를 거치지 않고 퍼블릭 ALB로 직접 들어갑니다.

## 주요 설정값 (cdk.json)

| 키 | 기본값 | 설명 |
|---|---|---|
| `environment` | `dev` | 배포 환경 |
| `region` | `ap-northeast-2` | AWS 리전 |
| `app_name` | `claude-proxy` | 리소스 이름 접두사 |
| `identity_store_id` | _(필수)_ | IAM Identity Center identity store ID |
| `vpc_cidr` | `10.0.0.0/16` | VPC CIDR |
| `aurora_min_capacity` | `0.5` | Aurora Serverless 최소 ACU |
| `aurora_max_capacity` | `1.0` | Aurora Serverless 최대 ACU |
| `acm_certificate_arn` | _(없음)_ | ACM 인증서 ARN (없으면 HTTP만) |
