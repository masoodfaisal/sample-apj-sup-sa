"""AlbConstruct for the Application Load Balancer and associated resources."""

from __future__ import annotations

from aws_cdk import Duration
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from constructs import Construct

from infra.config import InfraContext
from infra.cdk_constructs.network import NetworkConstruct


class AlbConstruct(Construct):
    """Provision the ALB, target group, and listeners."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        context: InfraContext,
        network: NetworkConstruct,
    ) -> None:
        super().__init__(scope, construct_id)

        certificate_arn = context.acm_certificate_arn

        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "GatewayAlb",
            load_balancer_name=context.resource_name("alb"),
            vpc=network.vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=network.public_subnets),
            security_group=network.alb_sg,
            internet_facing=True,
            idle_timeout=Duration.seconds(600),
            deletion_protection=context.is_prod,
            drop_invalid_header_fields=True,
        )

        self.gateway_target_group = elbv2.ApplicationTargetGroup(
            self,
            "GatewayTargetGroup",
            target_group_name=context.resource_name("gateway-tg"),
            vpc=network.vpc,
            target_type=elbv2.TargetType.IP,
            protocol=elbv2.ApplicationProtocol.HTTP,
            port=8000,
            health_check=elbv2.HealthCheck(
                path="/v1/healthz",
                protocol=elbv2.Protocol.HTTP,
                port="8000",
                interval=Duration.seconds(10),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=2,
            ),
            deregistration_delay=Duration.seconds(30),
        )

        if certificate_arn:
            self.https_listener = self.alb.add_listener(
                "HttpsListener",
                port=443,
                protocol=elbv2.ApplicationProtocol.HTTPS,
                certificates=[elbv2.ListenerCertificate.from_arn(certificate_arn)],
                ssl_policy=elbv2.SslPolicy.RECOMMENDED_TLS,
                default_action=elbv2.ListenerAction.forward([self.gateway_target_group]),
            )
            self.http_listener = self.alb.add_listener(
                "HttpListener",
                port=80,
                protocol=elbv2.ApplicationProtocol.HTTP,
                default_action=elbv2.ListenerAction.redirect(
                    protocol="HTTPS",
                    port="443",
                    permanent=True,
                ),
            )
        else:
            self.http_listener = self.alb.add_listener(
                "HttpListener",
                port=80,
                protocol=elbv2.ApplicationProtocol.HTTP,
                default_action=elbv2.ListenerAction.forward([self.gateway_target_group]),
            )
