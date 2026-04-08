"""Shared context parsing and naming helpers for the CDK app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aws_cdk import App, Duration, Environment, RemovalPolicy
from aws_cdk import aws_logs as logs

DEFAULT_REGION = "ap-northeast-2"
DEFAULT_APP_NAME = "claude-code-proxy"


def _get_context_value(app: App, key: str, default: Any = None) -> Any:
    value = app.node.try_get_context(key)
    return default if value is None else value


@dataclass(frozen=True, slots=True)
class InfraContext:
    """Normalized CDK context values used across stacks."""

    environment: str
    region: str
    app_name: str
    vpc_cidr: str
    public_subnet_mask: int
    private_app_subnet_mask: int
    private_data_subnet_mask: int
    aurora_min_capacity: float
    aurora_max_capacity: float
    aurora_backup_retention_days: int
    aurora_backup_window: str
    aurora_maintenance_window: str
    ecr_untagged_retention_days: int
    ecr_tagged_image_count: int
    identity_store_id: str
    identity_store_region: str
    acm_certificate_arn: str | None

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"

    @property
    def log_retention(self) -> logs.RetentionDays:
        return logs.RetentionDays.ONE_MONTH if self.is_prod else logs.RetentionDays.ONE_WEEK

    @property
    def resource_removal_policy(self) -> RemovalPolicy:
        return RemovalPolicy.RETAIN if self.is_prod else RemovalPolicy.DESTROY

    @property
    def aurora_backup_retention(self) -> Duration:
        return Duration.days(self.aurora_backup_retention_days)

    def stack_name(self, layer: str) -> str:
        return f"{self.app_name}-{self.environment}-{layer}"

    def resource_name(self, resource_type: str) -> str:
        return f"{self.app_name}-{self.environment}-{resource_type}"

    def secret_name(self, suffix: str) -> str:
        return f"{self.app_name}/{self.environment}/{suffix}"

    def kms_alias(self, suffix: str) -> str:
        return f"alias/{self.resource_name(suffix)}"


def load_context(app: App) -> InfraContext:
    """Build an InfraContext from CDK app context values."""

    return InfraContext(
        environment=str(_get_context_value(app, "environment", "dev")),
        region=str(_get_context_value(app, "region", DEFAULT_REGION)),
        app_name=str(_get_context_value(app, "app_name", DEFAULT_APP_NAME)),
        vpc_cidr=str(_get_context_value(app, "vpc_cidr", "10.0.0.0/16")),
        public_subnet_mask=int(_get_context_value(app, "public_subnet_mask", 24)),
        private_app_subnet_mask=int(_get_context_value(app, "private_app_subnet_mask", 20)),
        private_data_subnet_mask=int(_get_context_value(app, "private_data_subnet_mask", 24)),
        aurora_min_capacity=float(_get_context_value(app, "aurora_min_capacity", 1.0)),
        aurora_max_capacity=float(_get_context_value(app, "aurora_max_capacity", 1.0)),
        aurora_backup_retention_days=int(
            _get_context_value(app, "aurora_backup_retention_days", 7)
        ),
        aurora_backup_window=str(_get_context_value(app, "aurora_backup_window", "02:00-03:00")),
        aurora_maintenance_window=str(
            _get_context_value(app, "aurora_maintenance_window", "Sun:09:00-Sun:10:00")
        ),
        ecr_untagged_retention_days=int(_get_context_value(app, "ecr_untagged_retention_days", 30)),
        ecr_tagged_image_count=int(_get_context_value(app, "ecr_tagged_image_count", 10)),
        identity_store_id=str(_get_context_value(app, "identity_store_id", "placeholder")),
        identity_store_region=str(_get_context_value(app, "identity_store_region", "")),
        acm_certificate_arn=_coerce_optional_str(_get_context_value(app, "acm_certificate_arn")),
    )


def build_environment(context: InfraContext, account: str | None = None) -> Environment:
    """Create a CDK environment object for a given deployment account."""

    return Environment(account=account, region=context.region)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _coerce_optional_str(value: Any) -> str | None:
    """Return None for absent, None, or empty-string context values."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
