"""ObservabilityConstruct for Amazon Managed Prometheus."""

from __future__ import annotations

from aws_cdk import Aws
from aws_cdk import aws_aps as aps
from constructs import Construct

from infra.config import InfraContext


class ObservabilityConstruct(Construct):
    """Provision observability primitives: AMP."""

    def __init__(self, scope: Construct, construct_id: str, *, context: InfraContext) -> None:
        super().__init__(scope, construct_id)
        self.context = context

        # --- Amazon Managed Prometheus ---
        self.amp_workspace = aps.CfnWorkspace(
            self,
            "AmpWorkspace",
            alias=context.resource_name("amp"),
        )
        self.amp_workspace_id = self.amp_workspace.attr_workspace_id
        self.amp_workspace_arn = self.amp_workspace.attr_arn
        self.amp_remote_write_url = (
            f"https://aps-workspaces."
            f"{Aws.REGION}.amazonaws.com/workspaces/{self.amp_workspace_id}/api/v1/remote_write"
        )
