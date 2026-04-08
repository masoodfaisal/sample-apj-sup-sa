"""CDK app entrypoint for the Unit 1 infrastructure scaffold."""

from __future__ import annotations

import os
from dataclasses import dataclass

from aws_cdk import App, Tags

from infra.config import build_environment, load_context
from infra.stacks.foundation_stack import FoundationStack
from infra.stacks.service_stack import ServiceStack


@dataclass(frozen=True, slots=True)
class StackBundle:
    """Convenient accessors for all stacks created by the CDK app."""

    foundation: FoundationStack
    service: ServiceStack


def build_stacks(app: App, *, account: str | None = None) -> StackBundle:
    """Create all Unit 1 stacks with explicit dependencies."""

    context = load_context(app)
    deployment_env = build_environment(
        context,
        account=account or os.getenv("CDK_DEFAULT_ACCOUNT"),
    )

    Tags.of(app).add("Project", context.app_name)
    Tags.of(app).add("Environment", context.environment)
    Tags.of(app).add("ManagedBy", "cdk")

    foundation = FoundationStack(
        app,
        context.stack_name("foundation"),
        context=context,
        env=deployment_env,
    )
    service = ServiceStack(
        app,
        context.stack_name("service"),
        context=context,
        foundation=foundation,
        env=deployment_env,
    )
    service.add_dependency(foundation)

    return StackBundle(
        foundation=foundation,
        service=service,
    )


def main() -> None:
    """Entrypoint used by CDK and local synthesis."""

    app = App()
    build_stacks(app)
    app.synth()


if __name__ == "__main__":
    main()
