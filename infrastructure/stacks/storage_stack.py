from aws_cdk import (
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_amazonmq as mq,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_rds as rds,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_secretsmanager as sm,
)
from constructs import Construct
from stacks.network_stack import NetworkStack


class StorageStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        network: NetworkStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self,
            "DocumentsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.db_secret = sm.Secret(
            self,
            "DbSecret",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"username": "docpipeline"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        self.db = rds.DatabaseInstance(
            self,
            "Db",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16
            ),
            database_name="docpipelinedb",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
            vpc=network.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[network.rds_sg],
            credentials=rds.Credentials.from_secret(self.db_secret),  # type: ignore
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.mq_secret = sm.Secret(
            self,
            "MqSecret",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"username": "docpipeline"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        self.mq = mq.CfnBroker(
            self,
            "Broker",
            broker_name="doc-pipeline-broker",
            engine_type="RABBITMQ",
            engine_version="3.13",
            host_instance_type="mq.m5.large",
            deployment_mode="SINGLE_INSTANCE",
            publicly_accessible=False,
            subnet_ids=[network.vpc.private_subnets[0].subnet_id],
            security_groups=[network.mq_sg.security_group_id],
            users=[
                mq.CfnBroker.UserProperty(
                    username=self.mq_secret.secret_value_from_json(
                        "username"
                    ).unsafe_unwrap(),
                    password=self.mq_secret.secret_value_from_json(
                        "password"
                    ).unsafe_unwrap(),
                )
            ],
        )
