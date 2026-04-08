"""ServiceStack — ECS, ALB, API Gateway, and Observability."""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from infra.config import InfraContext
from infra.cdk_constructs.alb import AlbConstruct
from infra.cdk_constructs.api import ApiConstruct
from infra.cdk_constructs.compute import ComputeConstruct
from infra.cdk_constructs.observability import ObservabilityConstruct
from infra.stacks.foundation_stack import FoundationStack


class ServiceStack(Stack):
    """Provision service-layer resources on top of the foundation."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        context: InfraContext,
        foundation: FoundationStack,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        network = foundation.network
        data = foundation.data

        self.observability = ObservabilityConstruct(self, "Observability", context=context)
        self.compute = ComputeConstruct(
            self, "Compute", context=context, network=network, data=data, observability=self.observability,
        )
        self.alb = AlbConstruct(self, "Alb", context=context, network=network)
        self.api = ApiConstruct(
            self, "Api", context=context, network=network, compute=self.compute,
            alb=self.alb, data=data, observability=self.observability,
        )

        # --- Outputs ---
        CfnOutput(self, "AmpWorkspaceId", value=self.observability.amp_workspace_id)
        CfnOutput(self, "AmpWorkspaceArn", value=self.observability.amp_workspace_arn)
        CfnOutput(self, "AmpRemoteWriteUrl", value=self.observability.amp_remote_write_url)
        CfnOutput(self, "GatewayClusterName", value=self.compute.ecs_cluster.cluster_name)
        CfnOutput(self, "GatewayRepositoryUri", value=self.compute.gateway_ecr_repository.repository_uri)
        CfnOutput(self, "AlbDnsName", value=self.alb.alb.load_balancer_dns_name)
        CfnOutput(self, "TokenApiUrl", value=self.api.token_api.url)
        CfnOutput(self, "GatewayServiceName", value=self.api.gateway_service.service_name)
        CfnOutput(
            self,
            "GatewayTargetGroupArn",
            value=self.alb.gateway_target_group.target_group_arn,
        )
