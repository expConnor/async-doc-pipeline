#!/usr/bin/env python3

import os

import aws_cdk as cdk
from stacks.network_stack import NetworkStack

app = cdk.App()
network = NetworkStack(
    app,
    "DocPipelineNetwork",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("AWS_REGION", "us-east-1"),
    ),
)

app.synth()
