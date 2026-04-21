from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER_PATH = REPO_ROOT / "scripts" / "api_key_helper.local.sh"


def _write_fake_curl(tmp_path: Path) -> Path:
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env python3
import os
import sys

args_file = os.environ["FAKE_CURL_ARGS_FILE"]
response_body = os.environ.get("FAKE_CURL_RESPONSE_BODY", '{"virtual_key":{"secret":"vk-local-issued"}}')

with open(args_file, "w", encoding="utf-8") as handle:
    handle.write("\\n".join(sys.argv[1:]))

sys.stdout.write(response_body)
""",
        encoding="utf-8",
    )
    fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IXUSR)
    return fake_curl


def test_local_api_key_helper_calls_token_service(tmp_path: Path) -> None:
    _write_fake_curl(tmp_path)
    args_file = tmp_path / "curl.args"

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["FAKE_CURL_ARGS_FILE"] = str(args_file)
    env["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:8000"
    env["AWS_PROFILE"] = "local-dev"

    result = subprocess.run(
        ["bash", str(HELPER_PATH)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "vk-local-issued"

    args = args_file.read_text(encoding="utf-8")
    assert "http://127.0.0.1:8000/v1/auth/token" in args
    assert "x-auth-origin: apigw" in args
    assert "x-auth-principal: arn:aws:sts::local:assumed-role/GatewayAuth/local-user" in args
    assert '"client_name": "claude-code"' in args
    assert '"aws_profile": "local-dev"' in args


def test_local_api_key_helper_surfaces_error_payloads(tmp_path: Path) -> None:
    _write_fake_curl(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["FAKE_CURL_ARGS_FILE"] = str(tmp_path / "curl.args")
    env["FAKE_CURL_RESPONSE_BODY"] = '{"error":{"code":"authentication_failed"}}'
    env["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:8000"

    result = subprocess.run(
        ["bash", str(HELPER_PATH)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )

    assert result.returncode == 1
    assert (
        'ERROR: Failed to retrieve key from local token service: '
        '{"error":{"code":"authentication_failed"}}'
    ) in result.stderr
