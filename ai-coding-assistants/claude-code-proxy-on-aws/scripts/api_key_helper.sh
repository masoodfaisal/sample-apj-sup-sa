#!/usr/bin/env bash
set -euo pipefail

API_GW_ID="${API_GW_ID:-your-apigateway-id}"
AWS_REGION="${AWS_REGION:-ap-northeast-2}"
AWS_PROFILE=${AWS_PROFILE:-ccob}
TOKEN_SERVICE_URL="https://${API_GW_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod/v1/auth/token"

if ! eval "$(aws configure export-credentials --profile ${AWS_PROFILE} --format env 2>/dev/null)"; then
  if [[ -n "${AWS_PROFILE}" ]]; then
    echo "ERROR: Run 'aws sso login --profile ${AWS_PROFILE}'" >&2
  else
    echo "ERROR: Run 'aws sso login'" >&2
  fi
  exit 1
fi

RESPONSE="$(curl -sS -X POST "${TOKEN_SERVICE_URL}" \
  --aws-sigv4 "aws:amz:${AWS_REGION}:execute-api" \
  --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" \
  -H "x-amz-security-token: ${AWS_SESSION_TOKEN:-}" \
  -H "Content-Type: application/json" \
  -d '{}' 2>/dev/null)"

TOKEN="$(printf '%s' "${RESPONSE}" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)

print(payload.get("virtual_key", {}).get("secret", ""))
' 2>/dev/null)"

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: Failed to retrieve key from token service: ${RESPONSE}" >&2
  exit 1
fi

printf '%s\n' "${TOKEN}"
