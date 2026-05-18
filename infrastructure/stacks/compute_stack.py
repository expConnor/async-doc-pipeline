from aws_cdk import (
    Fn,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_elasticloadbalancingv2 as elbv2,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_logs as logs,
)
from constructs import Construct
from stacks.ecr_stack import ECRStack
from stacks.network_stack import NetworkStack
from stacks.storage_stack import StorageStack


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        network: NetworkStack,
        storage: StorageStack,
        ecr: ECRStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cluster = ecs.Cluster(self, "Cluster", vpc=network.vpc)

        api_log_group = logs.LogGroup(
            self,
            "ApiLogGroup",
            log_group_name="/doc-pipeline/api",
            removal_policy=RemovalPolicy.DESTROY,
        )
        worker_log_group = logs.LogGroup(
            self,
            "WorkerLogGroup",
            log_group_name="/doc-pipeline/worker",
            removal_policy=RemovalPolicy.DESTROY,
        )

        api_role = iam.Role(
            self,
            "ApiTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),  # type: ignore
        )
        storage.bucket.grant_read_write(api_role)
        storage.db_secret.grant_read(api_role)
        storage.mq_secret.grant_read(api_role)

        worker_role = iam.Role(
            self,
            "WorkerTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),  # type: ignore
        )
        storage.bucket.grant_read_write(worker_role)
        storage.db_secret.grant_read(worker_role)
        storage.mq_secret.grant_read(worker_role)

        mq_endpoint = Fn.select(0, storage.mq.attr_amqp_endpoints)
        mq_host = Fn.select(
            0, Fn.split(":", Fn.select(1, Fn.split("//", mq_endpoint)))
        )

        shared_env = {
            "POSTGRES_HOST": storage.db.db_instance_endpoint_address,
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "doc-pipeline-db",
            "S3_BUCKET": storage.bucket.bucket_name,
            "RABBITMQ_HOST": mq_host,
            "RABBITMQ_PORT": "5671",
            "RABBITMQ_QUEUE": "jobs",
            "APP_ENV": "prod",
        }
        shared_secrets = {
            "POSTGRES_USER": ecs.Secret.from_secrets_manager(
                storage.db_secret,  # type: ignore
                "username",
            ),
            "POSTGRES_PASSWORD": ecs.Secret.from_secrets_manager(
                storage.db_secret,  # type: ignore
                "password",
            ),
            "RABBITMQ_USER": ecs.Secret.from_secrets_manager(
                storage.mq_secret,  # type: ignore
                "username",
            ),
            "RABBITMQ_PASSWORD": ecs.Secret.from_secrets_manager(
                storage.mq_secret,  # type: ignore
                "password",
            ),
        }

        api_task_def = ecs.FargateTaskDefinition(
            self,
            "ApiTaskDef",
            cpu=512,
            memory_limit_mib=1024,
            task_role=api_role,  # type: ignore
        )
        api_task_def.add_container(
            "ApiContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr.api_repo),
            environment=shared_env,
            secrets=shared_secrets,
            port_mappings=[ecs.PortMapping(container_port=8080)],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="api",
                log_group=api_log_group,
            ),
        )

        worker_task_def = ecs.FargateTaskDefinition(
            self,
            "WorkerTaskDef",
            cpu=1024,
            memory_limit_mib=2048,
            task_role=worker_role,  # type: ignore
        )
        worker_task_def.add_container(
            "WorkerContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr.worker_repo),
            environment=shared_env,
            secrets=shared_secrets,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="worker",
                log_group=worker_log_group,
            ),
        )

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "Alb",
            vpc=network.vpc,
            internet_facing=True,
            security_group=network.alb_sg,
        )
        listener = alb.add_listener("HttpListener", port=80)

        api_service = ecs.FargateService(
            self,
            "ApiService",
            cluster=cluster,
            task_definition=api_task_def,
            security_groups=[network.api_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            desired_count=1,
        )
        listener.add_targets(
            "ApiTarget",
            port=8080,
            targets=[api_service],
            health_check=elbv2.HealthCheck(path="/health"),
        )

        ecs.FargateService(
            self,
            "WorkerService",
            cluster=cluster,
            task_definition=worker_task_def,
            security_groups=[network.worker_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            desired_count=1,
        )

        self.alb_dns = alb.load_balancer_dns_name
