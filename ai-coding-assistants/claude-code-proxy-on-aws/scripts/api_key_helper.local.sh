#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${LOCAL_GATEWAY_BASE_URL:-${ANTHROPIC_BASE_URL:-http://127.0.0.1:8000}}"
TOKEN_SERVICE_URL="${LOCAL_GATEWAY_TOKEN_URL:-${BASE_URL%/}/v1/auth/token}"
AUTH_ORIGIN="${LOCAL_GATEWAY_AUTH_ORIGIN:-apigw}"
AUTH_PRINCIPAL="${LOCAL_GATEWAY_AUTH_PRINCIPAL_ARN:-arn:aws:sts::local:assumed-role/GatewayAuth/local-user}"

REQUEST_BODY="$(python3 - <<'PY'
import json
import os

payload = {"client_name": "claude-code"}
aws_profile = os.getenv("AWS_PROFILE")
if aws_profile:
    payload["aws_profile"] = aws_profile

print(json.dumps(payload))
PY
)"

RESPONSE="$(curl -sS -X POST "${TOKEN_SERVICE_URL}" \
  -H "Content-Type: application/json" \
  -H "x-auth-origin: ${AUTH_ORIGIN}" \
  -H "x-auth-principal: ${AUTH_PRINCIPAL}" \
  -d "${REQUEST_BODY}")"

TOKEN="$(printf '%s' "${RESPONSE}" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)

print(payload.get("virtual_key", {}).get("secret", ""))
')"

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: Local token service에서 키를 받지 못했습니다: ${RESPONSE}" >&2
  exit 1
fi

printf '%s\n' "${TOKEN}"
