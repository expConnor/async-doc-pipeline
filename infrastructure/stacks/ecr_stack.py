from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class ECRStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.api_repo = ecr.Repository(
            self,
            "ApiRepo",
            repository_name="doc-pipeline-api",
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.worker_repo = ecr.Repository(
            self,
            "WorkerRepo",
            repository_name="doc-pipeline-worker",
            removal_policy=RemovalPolicy.RETAIN,
        )
