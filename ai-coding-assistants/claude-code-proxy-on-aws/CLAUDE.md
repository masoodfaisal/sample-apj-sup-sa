# CLAUDE.md

## Project

Claude Code Proxy on AWS is an Anthropic-compatible proxy on AWS.

- `gateway/`: FastAPI runtime, admin, and identity sync APIs
- `shared/`: shared models, schemas, and utilities
- `migrations/`: database schema source of truth
- `infra/`: AWS CDK stacks and deployment shape

## SSoT

Trust sources in this order:

- Code and wiring: `gateway/`, `shared/`, `infra/`
- Schema: `migrations/versions/001_initial_schema.py`
- Code-aligned docs: `docs/README.md`
- Archive only: `docs/aidlc-docs.backup.zip`

Read first, in order:

- `README.md`
- `docs/README.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- `docs/API_SPEC.md`
- `docs/DATA_MODEL.md`
- `docs/RUNTIME_TRANSLATION.md`
- `infra/README.md` for CDK and deployment work

If code, migration, and docs disagree, trust code and migration, then fix docs.

## Five Principles

1. Keep this file high-signal. Do not copy what agents can already infer from code or tree shape.
2. Treat `docs/` as indexed SSoT, not parallel truth. Update the matching doc in the same change when behavior changes.
3. Use progressive disclosure. Read the task-specific doc first, then only the relevant entry points.
4. Encode operational constraints and landmines here, not generic style advice.
5. Grow this file from repeated failures, and shrink it when code or docs become clear enough.

## Working Rules

- Use `uv` for Python environment and dependency management.
- The repo targets Python `>=3.13,<3.14`.
- Use `uv sync --group dev --group infra` for local setup when CDK or stack tests are needed.
- Reuse existing code in `shared/models/`, `shared/schemas/`, `shared/utils/`, and `gateway/repositories/` before adding duplicates.
- If API behavior changes, update `docs/API_SPEC.md`.
- If runtime translation changes, update `docs/RUNTIME_TRANSLATION.md`.
- If schema or state semantics change, update `docs/DATA_MODEL.md` and the relevant migration or model code.
- If infra topology or deployment semantics change, update `docs/SYSTEM_ARCHITECTURE.md` and/or `infra/README.md`.
- Treat `docs/aidlc-docs.backup.zip` as historical rationale only, never current truth.

## Fast Paths

- Runtime: `gateway/main.py`, `gateway/domains/runtime/router.py`, `gateway/domains/runtime/services.py`, `gateway/core/dependencies.py`, `gateway/domains/policy/`
- Token issuance: `gateway/domains/auth/router.py`, `gateway/domains/auth/service.py`, `gateway/core/dependencies.py`
- Admin and sync: `gateway/domains/admin/router.py`, `gateway/domains/admin/`
- Schema and persistence: `migrations/versions/001_initial_schema.py`, `shared/models/`, `gateway/repositories/`
- Infra: `infra/app.py`, `infra/stacks/`, `Dockerfile`

## Landmines

- Runtime health path is `GET /v1/healthz`, not `/healthz`.
- `GET /v1/models` authenticates the caller, but it does not currently filter models by user or team policy.
- Model fallback is data-driven through `model_alias_mappings.is_fallback`; there is no hardcoded fallback model name.
- Admin access requires trusted `x-admin-origin` and present `x-admin-principal`.
- Identity sync refreshes active users and marks missing users `INACTIVE` with `source_deleted_at`.
- Usage aggregate tables and read APIs exist, but runtime does not currently populate them.
- Gateway can emit OTLP metrics when `OTLP_GRPC_ENDPOINT` is configured, but local compose disables export by default and does not provision a local collector.

## Default Workflow

1. Read `docs/README.md` and the task-specific SSoT doc.
2. Read only the relevant code entry points.
3. Make the smallest coherent change.
4. Update the matching doc in the same change if behavior changed.
5. Verify narrowly before widening scope.

## Agent Mistake Log

Record repeated agent mistakes in this section. If the same avoidable mistake happens twice, add a dated bullet here with the symptom, the correct rule, and where to look next time. Record it here, not in a separate note.

- Add new entries below this line.
- 2026-04-05: Prematurely terminated error-path review without tracing to the end. In `sync/services.py`, failed to see that `update_run_by_id(FAILED)` correctly handles the state after rollback, and incorrectly reported "STARTED row persists permanently." **Rule**: When reviewing error paths, always trace completely through code after rollback/catch. Even when confident a bug has been found, read to the end of the code block.
