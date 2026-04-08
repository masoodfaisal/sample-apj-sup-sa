"""Initial shared schema."""

# ruff: noqa: E501

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


UUID = sa.Uuid(as_uuid=True)
ZERO_UUID_SQL = "'00000000-0000-0000-0000-000000000000'::uuid"


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_teams_status", "teams", ["status"])

    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("identity_store_user_id", sa.Text(), nullable=False, unique=True),
        sa.Column("user_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'INACTIVE'")),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("default_team_id", UUID, sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_status", "users", ["status"])
    op.create_index("ix_users_last_synced_at", "users", [sa.text("last_synced_at DESC")])
    op.create_index("ix_users_last_login_at", "users", [sa.text("last_login_at DESC")])

    op.create_table(
        "team_memberships",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'ADMIN'")),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'MEMBER'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "team_id", name="uq_team_memberships_user_team"),
    )

    op.create_table(
        "model_catalog",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False, unique=True),
        sa.Column("bedrock_model_id", sa.Text(), nullable=False, unique=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("family", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("supports_streaming", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supports_prompt_cache", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("default_max_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "virtual_keys",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_fingerprint", sa.Text(), nullable=False, unique=True),
        sa.Column("key_last4", sa.Text(), nullable=False),
        sa.Column("kms_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_virtual_keys_active_user",
        "virtual_keys",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "model_alias_mappings",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("selected_model_pattern", sa.Text(), nullable=False),
        sa.Column("target_model_id", UUID, sa.ForeignKey("model_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "selected_model_pattern",
            "priority",
            name="uq_model_alias_mappings_pattern_priority",
        ),
    )
    op.create_index(
        "uq_model_alias_mappings_fallback",
        "model_alias_mappings",
        ["is_fallback"],
        unique=True,
        postgresql_where=sa.text("is_fallback = true"),
    )

    op.create_table(
        "model_pricing",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("model_id", UUID, sa.ForeignKey("model_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("input_price_per_1k", sa.Numeric(18, 8), nullable=False),
        sa.Column("output_price_per_1k", sa.Numeric(18, 8), nullable=False),
        sa.Column("cache_read_price_per_1k", sa.Numeric(18, 8), nullable=False),
        sa.Column("cache_write_5m_price_per_1k", sa.Numeric(18, 8), nullable=False),
        sa.Column("cache_write_1h_price_per_1k", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("model_id", "effective_from", name="uq_model_pricing_model_effective"),
        sa.CheckConstraint("input_price_per_1k >= 0", name="ck_model_pricing_input_price_non_negative"),
        sa.CheckConstraint("output_price_per_1k >= 0", name="ck_model_pricing_output_price_non_negative"),
        sa.CheckConstraint(
            "cache_read_price_per_1k >= 0",
            name="ck_model_pricing_cache_read_price_non_negative",
        ),
        sa.CheckConstraint(
            "cache_write_5m_price_per_1k >= 0",
            name="ck_model_pricing_cache_write_5m_price_non_negative",
        ),
        sa.CheckConstraint(
            "cache_write_1h_price_per_1k >= 0",
            name="ck_model_pricing_cache_write_1h_price_non_negative",
        ),
    )

    op.create_table(
        "user_model_policies",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", UUID, sa.ForeignKey("model_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allow", sa.Boolean(), nullable=False),
        sa.Column("cache_policy", sa.Text(), nullable=True),
        sa.Column("max_tokens_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "model_id", name="uq_user_model_policies_pair"),
    )

    op.create_table(
        "team_model_policies",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", UUID, sa.ForeignKey("model_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allow", sa.Boolean(), nullable=False),
        sa.Column("cache_policy", sa.Text(), nullable=True),
        sa.Column("max_tokens_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("team_id", "model_id", name="uq_team_model_policies_pair"),
    )

    op.create_table(
        "budget_policies",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("scope_team_id", UUID, sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("model_id", UUID, sa.ForeignKey("model_catalog.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("soft_limit_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("hard_limit_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("current_used_usd", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "("
            "(scope_type = 'USER' AND scope_user_id IS NOT NULL AND scope_team_id IS NULL)"
            " OR "
            "(scope_type = 'TEAM' AND scope_team_id IS NOT NULL AND scope_user_id IS NULL)"
            ")",
            name="ck_budget_policies_scope_xor",
        ),
        sa.CheckConstraint("soft_limit_usd <= hard_limit_usd", name="ck_budget_policies_budget_limit_order"),
    )
    op.create_index(
        "ix_budget_policies_scope_lookup",
        "budget_policies",
        ["scope_type", "scope_user_id", "scope_team_id", "period", "active"],
    )
    op.create_index("ix_budget_policies_window_started_at", "budget_policies", ["window_started_at"])
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_budget_policies_user_active
        ON budget_policies (scope_user_id, period, coalesce(model_id, {ZERO_UUID_SQL}))
        WHERE scope_type = 'USER' AND active = true
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_budget_policies_team_active
        ON budget_policies (scope_team_id, period, coalesce(model_id, {ZERO_UUID_SQL}))
        WHERE scope_type = 'TEAM' AND active = true
        """
    )

    op.create_table(
        "identity_sync_runs",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("users_scanned", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("users_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("users_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("users_inactivated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("object_type", sa.Text(), nullable=False),
        sa.Column("object_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("sync_run_id", UUID, sa.ForeignKey("identity_sync_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "usage_events",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("virtual_key_id", UUID, sa.ForeignKey("virtual_keys.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("resolved_model_id", UUID, sa.ForeignKey("model_catalog.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("budget_policy_id", UUID, sa.ForeignKey("budget_policies.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("selected_model", sa.Text(), nullable=False),
        sa.Column("request_status", sa.Text(), nullable=False),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column("is_stream", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cached_read_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cached_write_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cache_details_json", sa.JSON(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("bedrock_invocation_id", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_usage_events_user_occurred_at", "usage_events", ["user_id", sa.text("occurred_at DESC")])
    op.create_index("ix_usage_events_team_occurred_at", "usage_events", ["team_id", sa.text("occurred_at DESC")])
    op.create_index(
        "ix_usage_events_model_occurred_at",
        "usage_events",
        ["resolved_model_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_usage_events_status_occurred_at",
        "usage_events",
        ["request_status", sa.text("occurred_at DESC")],
    )

    op.create_table(
        "usage_daily_agg",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("agg_date", sa.Date(), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("model_id", UUID, sa.ForeignKey("model_catalog.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("blocked_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cached_read_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cached_write_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_usage_daily_agg_grain
        ON usage_daily_agg (agg_date, user_id, model_id, coalesce(team_id, {ZERO_UUID_SQL}))
        """
    )

    op.create_table(
        "usage_monthly_agg",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("month_start", sa.Date(), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("model_id", UUID, sa.ForeignKey("model_catalog.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("blocked_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cached_read_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cached_write_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_usage_monthly_agg_grain
        ON usage_monthly_agg (month_start, user_id, model_id, coalesce(team_id, {ZERO_UUID_SQL}))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_usage_monthly_agg_grain")
    op.drop_table("usage_monthly_agg")
    op.execute("DROP INDEX IF EXISTS uq_usage_daily_agg_grain")
    op.drop_table("usage_daily_agg")
    op.drop_index("ix_usage_events_status_occurred_at", table_name="usage_events")
    op.drop_index("ix_usage_events_model_occurred_at", table_name="usage_events")
    op.drop_index("ix_usage_events_team_occurred_at", table_name="usage_events")
    op.drop_index("ix_usage_events_user_occurred_at", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_table("audit_events")
    op.drop_table("identity_sync_runs")
    op.execute("DROP INDEX IF EXISTS uq_budget_policies_team_active")
    op.execute("DROP INDEX IF EXISTS uq_budget_policies_user_active")
    op.drop_index("ix_budget_policies_window_started_at", table_name="budget_policies")
    op.drop_index("ix_budget_policies_scope_lookup", table_name="budget_policies")
    op.drop_table("budget_policies")
    op.drop_table("team_model_policies")
    op.drop_table("user_model_policies")
    op.drop_table("model_pricing")
    op.drop_index("uq_model_alias_mappings_fallback", table_name="model_alias_mappings")
    op.drop_table("model_alias_mappings")
    op.drop_index("uq_virtual_keys_active_user", table_name="virtual_keys")
    op.drop_table("virtual_keys")
    op.drop_table("model_catalog")
    op.drop_table("team_memberships")
    op.drop_index("ix_users_last_login_at", table_name="users")
    op.drop_index("ix_users_last_synced_at", table_name="users")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_teams_status", table_name="teams")
    op.drop_table("teams")
