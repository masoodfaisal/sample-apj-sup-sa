#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# Claude Code Proxy on AWS — 배포 스크립트
# ──────────────────────────────────────────────

INFRA_DIR="$(cd "$(dirname "$0")/../infra" && pwd)"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CDK_JSON="$INFRA_DIR/cdk.json"

# 색상
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
prompt() { echo -en "${CYAN}▸${NC} $*"; }

# ──────────────────────────────────────────────
# 1. 사전 요구사항 확인
# ──────────────────────────────────────────────
check_prerequisites() {
    info "사전 요구사항 확인 중..."

    command -v aws >/dev/null 2>&1 || error "AWS CLI가 설치되어 있지 않습니다."
    command -v cdk >/dev/null 2>&1 || error "CDK CLI가 설치되어 있지 않습니다. (npm install -g aws-cdk)"
    command -v docker >/dev/null 2>&1 || error "Docker가 설치되어 있지 않습니다."
    command -v uv >/dev/null 2>&1 || error "uv가 설치되어 있지 않습니다."
    command -v jq >/dev/null 2>&1 || error "jq가 설치되어 있지 않습니다."

    # Docker 실행 확인
    docker info >/dev/null 2>&1 || error "Docker 데몬이 실행중이지 않습니다."

    ok "사전 요구사항 확인 완료"
}

# ──────────────────────────────────────────────
# 2. AWS 인증 확인
# ──────────────────────────────────────────────
check_aws_auth() {
    info "AWS 인증 확인 중..."

    local identity
    identity=$(aws sts get-caller-identity 2>/dev/null) || error "AWS 인증 실패. 'aws configure' 또는 'aws sso login'을 실행하세요."

    local account
    account=$(echo "$identity" | jq -r '.Account')

    ok "AWS 계정: $account"
    export CDK_DEFAULT_ACCOUNT="$account"
}

# ──────────────────────────────────────────────
# 3. 리전 선택
# ──────────────────────────────────────────────
select_region() {
    local current_region
    current_region=$(jq -r '.context.region // "ap-northeast-2"' "$CDK_JSON")

    info "현재 설정된 리전: $current_region"
    prompt "배포할 리전 [$current_region]: "
    read -er input_region

    local region="${input_region:-$current_region}"

    if [[ "$region" != "$current_region" ]]; then
        _set_cdk_context "region" "$region"
        ok "리전 변경: $region"
    fi

    export CDK_DEFAULT_REGION="$region"
    ok "배포 리전: $region"
}

# ──────────────────────────────────────────────
# 4. Identity Store ID 선택
# ──────────────────────────────────────────────
select_identity_store_id() {
    local region current_id discovered_id
    region="$CDK_DEFAULT_REGION"
    current_id=$(jq -r '.context.identity_store_id // empty' "$CDK_JSON")
    DISCOVERED_IDENTITY_STORE_REGION=""
    discovered_id=$(_discover_identity_store_id "$region")

    if [[ -n "$discovered_id" && "$current_id" != "$discovered_id" ]]; then
        info "AWS에서 활성 Identity Store ID를 찾았습니다: $discovered_id (리전: ${DISCOVERED_IDENTITY_STORE_REGION:-$region})"
    fi

    local default_id="$current_id"
    if [[ -z "$default_id" || "$default_id" == "placeholder" ]]; then
        default_id="$discovered_id"
    fi

    if [[ -n "$default_id" ]]; then
        prompt "Identity Store ID [$default_id]: "
        read -er input_id
    else
        warn "활성 Identity Store ID를 자동으로 찾지 못했습니다."
        info "직접 확인 명령: aws sso-admin list-instances --region <region> --query 'Instances[].IdentityStoreId' --output text"
        prompt "Identity Store ID: "
        read -er input_id
    fi

    local identity_store_id="${input_id:-$default_id}"
    if [[ -z "$identity_store_id" || "$identity_store_id" == "placeholder" ]]; then
        error "Identity Store ID는 필수입니다. 올바른 값을 입력하세요."
    fi

    if [[ "$identity_store_id" != "$current_id" ]]; then
        _set_cdk_context "identity_store_id" "$identity_store_id"
        ok "Identity Store ID 설정 완료: $identity_store_id"
    else
        ok "Identity Store ID 유지: $identity_store_id"
    fi

    # Identity Store 리전 설정
    local current_region
    current_region=$(jq -r '.context.identity_store_region // empty' "$CDK_JSON")
    local default_region="${DISCOVERED_IDENTITY_STORE_REGION:-$current_region}"
    if [[ -z "$default_region" ]]; then
        default_region="$region"
    fi

    if [[ "$default_region" != "$region" ]]; then
        prompt "Identity Store 리전 [$default_region]: "
        read -er input_region
        local identity_store_region="${input_region:-$default_region}"
        _set_cdk_context "identity_store_region" "$identity_store_region"
        ok "Identity Store 리전 설정 완료: $identity_store_region"
    else
        _set_cdk_context "identity_store_region" "$region"
    fi
}

_discover_identity_store_id() {
    local region="$1"
    local search_regions=("$region" "us-east-1" "eu-west-1" "ap-southeast-1")
    for r in "${search_regions[@]}"; do
        local instances
        instances=$(aws sso-admin list-instances \
            --region "$r" \
            --query 'Instances[?Status==`ACTIVE`]' \
            --output json 2>/dev/null || true)

        if [[ -z "$instances" || "$instances" == "null" ]]; then
            continue
        fi

        local count
        count=$(echo "$instances" | jq 'length')
        if [[ "$count" -eq 1 ]]; then
            DISCOVERED_IDENTITY_STORE_REGION="$r"
            echo "$instances" | jq -r '.[0].IdentityStoreId'
            return 0
        fi

        if [[ "$count" -gt 1 ]]; then
            DISCOVERED_IDENTITY_STORE_REGION="$r"
            warn "활성 IAM Identity Center 인스턴스가 여러 개입니다 (리전: $r)." >&2
            echo "$instances" | jq -r '
                .[]
                | "  - IdentityStoreId: \(.IdentityStoreId)\n    OwnerAccountId: \(.OwnerAccountId)\n    InstanceArn: \(.InstanceArn)"
            ' >&2
        fi
    done
}

# ──────────────────────────────────────────────
# 5. ACM 인증서 확인/생성
# ──────────────────────────────────────────────
ensure_acm_certificate() {
    info "ACM 인증서 확인 중..."

    local existing_arn
    existing_arn=$(jq -r '.context.acm_certificate_arn // empty' "$CDK_JSON")

    if [[ -n "$existing_arn" ]]; then
        ok "ACM 인증서 설정됨: ${existing_arn:0:60}..."
        return
    fi

    warn "ACM 인증서가 cdk.json에 설정되어 있지 않습니다."
    echo ""
    echo "  1) 기존 ACM 인증서 ARN 입력"
    echo "  2) 새 ACM 인증서 생성 (도메인 필요)"
    echo "  3) 건너뛰기 (HTTPS 없이 HTTP만 사용)"
    echo ""
    while true; do
        prompt "선택 [1/2/3]: "
        read -er choice
        case "${choice}" in
            1)
                prompt "ACM 인증서 ARN: "
                read -er cert_arn
                [[ -z "$cert_arn" ]] && { warn "인증서 ARN이 비어있습니다."; continue; }
                _set_cdk_context "acm_certificate_arn" "$cert_arn"
                ok "ACM 인증서 설정 완료"
                break
                ;;
            2)
                _create_acm_certificate
                break
                ;;
            3)
                warn "HTTPS 없이 배포합니다. ALB는 HTTP(80)만 사용합니다."
                _set_cdk_context "acm_certificate_arn" ""
                export SKIP_HTTPS=true
                break
                ;;
            *)
                warn "1, 2, 3 중에서 선택하세요."
                ;;
        esac
    done
}

_create_acm_certificate() {
    prompt "도메인 이름 (예: proxy.example.com): "
    read -er domain
    [[ -z "$domain" ]] && error "도메인이 비어있습니다."

    local region
    region=$(jq -r '.context.region // "ap-northeast-2"' "$CDK_JSON")

    info "ACM 인증서 요청 중: $domain"
    local cert_arn
    cert_arn=$(aws acm request-certificate \
        --domain-name "$domain" \
        --validation-method DNS \
        --region "$region" \
        --query 'CertificateArn' \
        --output text)

    ok "인증서 요청 완료: $cert_arn"
    echo ""
    warn "DNS 검증이 필요합니다."
    info "검증 레코드 조회 중 (최대 30초 대기)..."

    local validation_info=""
    local attempt
    for attempt in $(seq 1 6); do
        sleep 5
        validation_info=$(aws acm describe-certificate \
            --certificate-arn "$cert_arn" \
            --region "$region" \
            --query 'Certificate.DomainValidationOptions[0].ResourceRecord' \
            --output json 2>/dev/null || true)
        if [[ -n "$validation_info" && "$validation_info" != "null" ]]; then
            break
        fi
        info "검증 레코드 대기 중... (${attempt}/6)"
    done

    if [[ -n "$validation_info" && "$validation_info" != "null" ]]; then
        local cname_name cname_value
        cname_name=$(echo "$validation_info" | jq -r '.Name')
        cname_value=$(echo "$validation_info" | jq -r '.Value')
        echo ""
        echo -e "  ${CYAN}DNS에 아래 CNAME 레코드를 추가하세요:${NC}"
        echo -e "  Name:  ${GREEN}$cname_name${NC}"
        echo -e "  Value: ${GREEN}$cname_value${NC}"
        echo ""
    else
        warn "검증 레코드를 가져오지 못했습니다. AWS 콘솔에서 직접 확인하세요: $cert_arn"
    fi

    prompt "DNS 레코드 추가 후 Enter를 눌러 검증을 기다립니다..."
    read -er

    info "인증서 검증 대기 중 (최대 5분)..."
    if aws acm wait certificate-validated \
        --certificate-arn "$cert_arn" \
        --region "$region" 2>/dev/null; then
        ok "인증서 검증 완료!"
    else
        warn "검증 대기 시간 초과. 배포를 계속하지만, 인증서 검증이 완료되어야 HTTPS가 동작합니다."
    fi

    _set_cdk_context "acm_certificate_arn" "$cert_arn"
    ok "cdk.json에 인증서 ARN 저장 완료"
}

_set_cdk_context() {
    local key="$1" value="$2"
    local tmp
    tmp=$(mktemp)
    jq --arg k "$key" --arg v "$value" '.context[$k] = $v' "$CDK_JSON" > "$tmp"
    mv "$tmp" "$CDK_JSON"
}

# ──────────────────────────────────────────────
# 6. CDK 부트스트랩
# ──────────────────────────────────────────────
ensure_bootstrap() {
    info "CDK 부트스트랩 확인 중..."

    local account region
    account="$CDK_DEFAULT_ACCOUNT"
    region="$CDK_DEFAULT_REGION"
    local min_version=30

    local stack_status
    stack_status=$(aws cloudformation describe-stacks \
        --stack-name CDKToolkit \
        --region "$region" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")

    local current_version=0
    if [[ "$stack_status" != "NOT_FOUND" ]]; then
        current_version=$(aws ssm get-parameter \
            --name "/cdk-bootstrap/hnb659fds/version" \
            --region "$region" \
            --query 'Parameter.Value' \
            --output text 2>/dev/null || echo "0")
    fi

    if [[ "$stack_status" == "NOT_FOUND" || "$stack_status" == *"ROLLBACK"* || "$current_version" -lt "$min_version" ]]; then
        info "CDK 부트스트랩 실행 중... (현재 버전: $current_version, 필요 버전: $min_version+)"
        cd "$INFRA_DIR"
        cdk bootstrap "aws://$account/$region"
        ok "CDK 부트스트랩 완료"
    else
        ok "CDK 부트스트랩 이미 완료 (버전: $current_version)"
    fi
}

# ──────────────────────────────────────────────
# 7. 의존성 설치
# ──────────────────────────────────────────────
install_dependencies() {
    info "Python 의존성 설치 중..."
    cd "$PROJECT_ROOT"
    uv sync --group dev --group infra
    ok "의존성 설치 완료"
}

# ──────────────────────────────────────────────
# 8. CDK 배포
# ──────────────────────────────────────────────
deploy_stacks() {
    cd "$INFRA_DIR"

    info "변경사항 확인 중..."
    echo ""
    cdk diff 2>&1 || true
    echo ""

    while true; do
        prompt "위 변경사항을 배포하시겠습니까? [y/N]: "
        read -er confirm
        case "${confirm}" in
            y|Y) break ;;
            n|N|"") info "배포를 취소합니다."; exit 0 ;;
            *) warn "y 또는 N을 입력하세요." ;;
        esac
    done

    info "CDK 스택 배포 중... (Docker 빌드 포함, 수 분 소요될 수 있습니다)"
    echo ""

    cdk deploy --all \
        --require-approval never \
        --no-path-metadata \
        --outputs-file "$PROJECT_ROOT/cdk-outputs.json"

    ok "배포 완료!"
    echo ""

    if [[ -f "$PROJECT_ROOT/cdk-outputs.json" ]]; then
        info "배포 결과:"
        jq '.' "$PROJECT_ROOT/cdk-outputs.json"
    fi
}

# ──────────────────────────────────────────────
# 9. CDK 삭제
# ──────────────────────────────────────────────
destroy_stacks() {
    cd "$INFRA_DIR"

    warn "모든 CDK 스택을 삭제합니다."
    echo ""
    echo "삭제될 스택:"
    cdk list 2>/dev/null || true
    echo ""

    while true; do
        prompt "정말 모든 스택을 삭제하시겠습니까? [y/N]: "
        read -er confirm
        case "${confirm}" in
            y|Y) break ;;
            n|N|"") info "삭제를 취소합니다."; exit 0 ;;
            *) warn "y 또는 N을 입력하세요." ;;
        esac
    done

    info "CDK 스택 삭제 중..."
    cdk destroy --all --force

    ok "모든 스택이 삭제되었습니다!"

    # cdk-outputs.json 삭제
    [[ -f "$PROJECT_ROOT/cdk-outputs.json" ]] && rm -f "$PROJECT_ROOT/cdk-outputs.json"
}

# ──────────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────────
usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  deploy   배포 (기본값)"
    echo "  destroy  모든 스택 삭제"
    echo ""
}

main() {
    if [[ "${1:-}" =~ ^(-h|--help|help)$ ]]; then usage; exit 0; fi

    local command="${1:-deploy}"

    echo ""
    echo -e "${CYAN} ██████╗██╗      █████╗ ██╗   ██╗██████╗ ███████╗     ██████╗ ██████╗ ██████╗ ███████╗${NC}"
    echo -e "${CYAN}██╔════╝██║     ██╔══██╗██║   ██║██╔══██╗██╔════╝    ██╔════╝██╔═══██╗██╔══██╗██╔════╝${NC}"
    echo -e "${CYAN}██║     ██║     ███████║██║   ██║██║  ██║█████╗      ██║     ██║   ██║██║  ██║█████╗  ${NC}"
    echo -e "${CYAN}██║     ██║     ██╔══██║██║   ██║██║  ██║██╔══╝      ██║     ██║   ██║██║  ██║██╔══╝  ${NC}"
    echo -e "${CYAN}╚██████╗███████╗██║  ██║╚██████╔╝██████╔╝███████╗    ╚██████╗╚██████╔╝██████╔╝███████╗${NC}"
    echo -e "${CYAN} ╚═════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝${NC}"
    echo -e "${CYAN}                                                                                      ${NC}"
    echo -e "${CYAN} ██████╗ ███╗   ██╗    ██████╗ ███████╗██████╗ ██████╗  ██████╗  ██████╗██╗  ██╗      ${NC}"
    echo -e "${CYAN}██╔═══██╗████╗  ██║    ██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔═══██╗██╔════╝██║ ██╔╝      ${NC}"
    echo -e "${CYAN}██║   ██║██╔██╗ ██║    ██████╔╝█████╗  ██║  ██║██████╔╝██║   ██║██║     █████╔╝       ${NC}"
    echo -e "${CYAN}██║   ██║██║╚██╗██║    ██╔══██╗██╔══╝  ██║  ██║██╔══██╗██║   ██║██║     ██╔═██╗       ${NC}"
    echo -e "${CYAN}╚██████╔╝██║ ╚████║    ██████╔╝███████╗██████╔╝██║  ██║╚██████╔╝╚██████╗██║  ██╗      ${NC}"
    echo -e "${CYAN} ╚═════╝ ╚═╝  ╚═══╝    ╚═════╝ ╚══════╝╚═════╝ ╚═╝  ╚═╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝      ${NC}"
    echo ""

    case "$command" in
        deploy)
            check_prerequisites
            check_aws_auth
            select_region
            select_identity_store_id
            install_dependencies
            ensure_acm_certificate
            ensure_bootstrap
            deploy_stacks
            echo ""
            ok "모든 배포가 완료되었습니다!"
            ;;
        destroy)
            check_prerequisites
            check_aws_auth
            select_region
            destroy_stacks
            ;;
        -h|--help|help)
            usage
            exit 0
            ;;
        *)
            error "알 수 없는 명령: $command"
            ;;
    esac
    echo ""
}

main "$@"
