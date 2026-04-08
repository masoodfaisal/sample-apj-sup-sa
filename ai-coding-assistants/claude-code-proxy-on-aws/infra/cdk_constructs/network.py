"""NetworkConstruct for Unit 1 foundation infrastructure."""

from __future__ import annotations

from typing import Any

from aws_cdk import Aws, Tags
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from constructs import Construct

from infra.config import InfraContext


class NetworkConstruct(Construct):
    """Provision the VPC, security groups, and VPC endpoints."""

    def __init__(self, scope: Construct, construct_id: str, *, context: InfraContext) -> None:
        super().__init__(scope, construct_id)
        self.context = context

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            vpc_name=context.resource_name("vpc"),
            ip_addresses=ec2.IpAddresses.cidr(context.vpc_cidr),
            max_azs=2,
            nat_gateways=1,
            enable_dns_hostnames=True,
            enable_dns_support=True,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=context.public_subnet_mask,
                ),
                ec2.SubnetConfiguration(
                    name="private-app",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=context.private_app_subnet_mask,
                ),
                ec2.SubnetConfiguration(
                    name="private-data",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=context.private_data_subnet_mask,
                ),
            ],
        )

        self.public_subnets = list(self.vpc.select_subnets(subnet_group_name="public").subnets)
        self.private_app_subnets = list(self.vpc.select_subnets(subnet_group_name="private-app").subnets)
        self.private_data_subnets = list(self.vpc.select_subnets(subnet_group_name="private-data").subnets)

        self.alb_sg = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=self.vpc,
            security_group_name=context.resource_name("alb-sg"),
            description="ALB ingress from internet and egress to ECS tasks",
        )
        self.ecs_sg = ec2.SecurityGroup(
            self,
            "EcsSecurityGroup",
            vpc=self.vpc,
            security_group_name=context.resource_name("ecs-sg"),
            description="Gateway ECS tasks",
        )
        self.endpoint_sg = ec2.SecurityGroup(
            self,
            "EndpointSecurityGroup",
            vpc=self.vpc,
            security_group_name=context.resource_name("endpoint-sg"),
            description="Interface VPC endpoints",
            allow_all_outbound=False,
        )

        self._configure_security_group_rules()
        self.interface_endpoints = self._create_interface_endpoints()
        self.s3_gateway_endpoint = self._create_s3_gateway_endpoint()

        Tags.of(self.alb_sg).add("Name", self.context.resource_name("alb-sg"))
        Tags.of(self.ecs_sg).add("Name", self.context.resource_name("ecs-sg"))
        Tags.of(self.endpoint_sg).add("Name", self.context.resource_name("endpoint-sg"))

    def _configure_security_group_rules(self) -> None:
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS from internet")
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP redirect from internet")
        self.ecs_sg.add_ingress_rule(
            ec2.Peer.security_group_id(self.alb_sg.security_group_id),
            ec2.Port.tcp(8000),
            "Ingress from ALB",
            remote_rule=True,
        )

        self.endpoint_sg.add_ingress_rule(
            ec2.Peer.security_group_id(self.ecs_sg.security_group_id),
            ec2.Port.tcp(443),
            "Ingress from ECS tasks",
            remote_rule=True,
        )

    def _create_interface_endpoints(self) -> dict[str, ec2.InterfaceVpcEndpoint]:
        account_condition = {
            "StringEquals": {"aws:PrincipalAccount": Aws.ACCOUNT_ID},
        }

        endpoint_specs: dict[str, tuple[ec2.IInterfaceVpcEndpointService, list[iam.PolicyStatement]]] = {
            "BedrockRuntime": (
                ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
                [
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        principals=[iam.AnyPrincipal()],
                        actions=[
                            "bedrock:InvokeModel",
                            "bedrock:InvokeModelWithResponseStream",
                        ],
                        resources=["*"],
                        conditions=account_condition,
                    )
                ],
            ),
            "EcrApi": (
                ec2.InterfaceVpcEndpointAwsService.ECR,
                self._scoped_endpoint_policy([
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchCheckLayerAvailability",
                ]),
            ),
            "EcrDocker": (
                ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
                self._scoped_endpoint_policy([
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchCheckLayerAvailability",
                ]),
            ),
            "CloudWatchLogs": (
                ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
                self._scoped_endpoint_policy([
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ]),
            ),
            "SecretsManager": (
                ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
                self._scoped_endpoint_policy([
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret",
                ]),
            ),
            "Kms": (
                ec2.InterfaceVpcEndpointAwsService.KMS,
                self._scoped_endpoint_policy([
                    "kms:Decrypt",
                    "kms:Encrypt",
                    "kms:GenerateDataKey",
                    "kms:DescribeKey",
                ]),
            ),
            "Sts": (
                ec2.InterfaceVpcEndpointAwsService.STS,
                self._scoped_endpoint_policy(["sts:AssumeRole", "sts:GetCallerIdentity"]),
            ),
            "Ecs": (
                ec2.InterfaceVpcEndpointAwsService.ECS,
                self._scoped_endpoint_policy([
                    "ecs:Poll",
                    "ecs:StartTelemetrySession",
                    "ecs:UpdateContainerInstancesState",
                    "ecs:RegisterContainerInstance",
                    "ecs:SubmitContainerStateChange",
                    "ecs:SubmitTaskStateChange",
                ]),
            ),
            "IdentityStore": (
                ec2.InterfaceVpcEndpointService(
                    f"com.amazonaws.{self.context.region}.identitystore",
                    443,
                ),
                self._scoped_endpoint_policy([
                    "identitystore:ListUsers",
                    "identitystore:DescribeUser",
                ]),
            ),
            "AmpWorkspaces": (
                ec2.InterfaceVpcEndpointService(
                    f"com.amazonaws.{self.context.region}.aps-workspaces",
                    443,
                ),
                self._scoped_endpoint_policy(["aps:*"]),
            ),
        }

        endpoints: dict[str, ec2.InterfaceVpcEndpoint] = {}
        for endpoint_name, (service, statements) in endpoint_specs.items():
            endpoint = self.vpc.add_interface_endpoint(
                f"{endpoint_name}Endpoint",
                service=service,
                subnets=ec2.SubnetSelection(subnets=self.private_app_subnets),
                security_groups=[self.endpoint_sg],
                private_dns_enabled=True,
            )
            for statement in statements:
                endpoint.add_to_policy(statement)
            endpoints[endpoint_name] = endpoint
        return endpoints

    def _create_s3_gateway_endpoint(self) -> ec2.GatewayVpcEndpoint:
        endpoint = self.vpc.add_gateway_endpoint(
            "S3GatewayEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnets=self.private_app_subnets)],
        )
        endpoint.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.AnyPrincipal()],
                actions=["s3:GetObject"],
                resources=[
                    f"arn:aws:s3:::prod-{self.context.region}-starport-layer-bucket/*",
                ],
            )
        )
        return endpoint

    def _scoped_endpoint_policy(self, actions: list[str]) -> list[iam.PolicyStatement]:
        """Create a least-privilege endpoint policy scoped to specific actions."""
        return [
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.AnyPrincipal()],
                actions=actions,
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "aws:PrincipalAccount": Aws.ACCOUNT_ID,
                    }
                },
            )
        ]
