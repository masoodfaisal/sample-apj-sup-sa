# Data Model

This document describes the relational model implemented by:

- [`migrations/versions/001_initial_schema.py`](/Users/jungseob/workspace/claude-code-proxy-on-aws/migrations/versions/001_initial_schema.py)
- [`shared/models/`](/Users/jungseob/workspace/claude-code-proxy-on-aws/shared/models)

## Source of Truth

- Schema truth is the Alembic migration.
- ORM shape and relationships live in `shared/models`.
- Query semantics live in `gateway/repositories`.

## Domain Groups

### Identity and access

- `users`
  - Identity Center-derived user record.
  - Default status is `INACTIVE`.
  - `default_team_id` is nullable.
- `teams`
  - Internal grouping managed by admin APIs.
  - Default status is `ACTIVE`.
- `team_memberships`
  - Unique on `(user_id, team_id)`.
  - Source defaults to `ADMIN`.
- `virtual_keys`
  - Stores hashed fingerprint plus KMS-encrypted secret.
  - Partial unique index enforces at most one `ACTIVE` key per user.

### Model catalog and policy

- `model_catalog`
  - Canonical model registry.
  - Stores Bedrock model id and capability flags such as streaming/tools/prompt cache support.
- `model_alias_mappings`
  - Maps client-selected model patterns to canonical models.
  - Ordered by `priority`.
  - At most one active fallback row via partial unique index on `is_fallback = true`.
- `model_pricing`
  - Time-versioned pricing rows per model.
  - Unique on `(model_id, effective_from)`.
- `user_model_policies`
  - Per-user allow/cache/max-token override.
  - Unique on `(user_id, model_id)`.
- `team_model_policies`
  - Per-team allow/cache/max-token override.
  - Unique on `(team_id, model_id)`.

### Budgets and usage

- `budget_policies`
  - Scope is XOR between user and team.
  - Scope type is `USER` or `TEAM`.
  - Model-specific and model-agnostic budgets are both supported.
  - Active uniqueness is enforced per `(scope, period, model_id|null)`.
- `usage_events`
  - Request-level usage ledger.
  - Unique on `request_id`.
  - Stores selected model, resolved model, status, token counts, cache counts, estimated cost, latency, and Bedrock invocation id.
- `usage_daily_agg`
- `usage_monthly_agg`
  - Aggregate tables exist with uniqueness on `(date grain, user_id, model_id, coalesce(team_id))`.
  - Current code exposes read repositories for these tables but does not populate them during runtime.

### Audit and sync

- `identity_sync_runs`
  - Manual sync run ledger.
- `audit_events`
  - Generic audit table for token issuance, token issuance failures, identity sync triggers, and selected admin operations.

## State Semantics

### Users

- Token issuance requires the user row to exist and be `ACTIVE`.
- Runtime access also requires `ACTIVE`.
- Manual Identity Center sync populates `last_synced_at`.
- Users returned by Identity Center have `source_deleted_at = null`.
- Users omitted from a sync run are marked `INACTIVE` and get `source_deleted_at`.
- Identity Center `UserStatus` is mapped to local `ACTIVE` or `INACTIVE` during sync.
- `last_login_at` exists in schema and DTOs, but current gateway code does not update it.

### Teams

- Runtime only considers `default_team_id`.
- If `default_team_id` is set, the referenced team must exist and be `ACTIVE`.

### Virtual keys

- Runtime validates keys by SHA-256 fingerprint lookup, not by decrypting stored ciphertext.
- Token service reuses an existing `ACTIVE` key if present, otherwise creates one.
- Admin rotation marks the previous key `ROTATED` and creates a new `ACTIVE` key.
- Admin revoke marks the key `REVOKED`.

### Model resolution

- `selected_model_pattern` is matched using `fnmatch`.
- Resolution order is descending `priority`; higher values are evaluated first.
- If no explicit pattern matches, the repository returns the first active fallback mapping, if one exists.
- There is no hardcoded fallback model name in code.

### Budget enforcement

- Pre-check handlers evaluate user, team, and model-scoped budgets before Bedrock invocation.
- Hard limit breach blocks the request.
- Soft limit breach records a warning in policy context.
- On successful usage recording, `current_used_usd` is incremented for all applicable budgets.
- Daily/monthly budget windows are reset lazily when a request is processed after the next period boundary.

## What Is Not Implemented Yet

- Automatic maintenance of `usage_daily_agg` and `usage_monthly_agg`
- A background rollup workflow or exposed admin rollup endpoint

## Files to Read by Task

- Schema change:
  [`migrations/versions/001_initial_schema.py`](/Users/jungseob/workspace/claude-code-proxy-on-aws/migrations/versions/001_initial_schema.py)
- ORM and relationships:
  [`shared/models/`](/Users/jungseob/workspace/claude-code-proxy-on-aws/shared/models)
- Query logic:
  [`gateway/repositories/`](/Users/jungseob/workspace/claude-code-proxy-on-aws/gateway/repositories)
