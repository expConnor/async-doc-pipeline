from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=1,
        )

        self.alb_sg = ec2.SecurityGroup(self, "AlbSg", vpc=self.vpc)
        self.api_sg = ec2.SecurityGroup(self, "ApiSg", vpc=self.vpc)
        self.worker_sg = ec2.SecurityGroup(self, "WorkerSg", vpc=self.vpc)
        self.rds_sg = ec2.SecurityGroup(self, "RdsSg", vpc=self.vpc)
        self.mq_sg = ec2.SecurityGroup(self, "MqSg", vpc=self.vpc)

        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        self.api_sg.add_ingress_rule(self.alb_sg, ec2.Port.tcp(8080))
        self.rds_sg.add_ingress_rule(self.api_sg, ec2.Port.tcp(5432))
        self.rds_sg.add_ingress_rule(self.worker_sg, ec2.Port.tcp(5432))
        self.mq_sg.add_ingress_rule(self.api_sg, ec2.Port.tcp(5671))
        self.mq_sg.add_ingress_rule(self.worker_sg, ec2.Port.tcp(5671))
