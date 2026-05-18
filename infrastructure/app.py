#!/usr/bin/env python3

import os

import aws_cdk as cdk
from stacks.compute_stack import ComputeStack
from stacks.ecr_stack import ECRStack
from stacks.network_stack import NetworkStack
from stacks.storage_stack import StorageStack

app = cdk.App()
env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("AWS_REGION", "us-east-1"),
)

network = NetworkStack(app, "DocPipelineNetwork", env=env)
storage = StorageStack(app, "DocPipelineStorage", network=network, env=env)
ecr_stack = ECRStack(app, "DocPipelineECR", env=env)
compute = ComputeStack(
    app,
    "DocPipelineCompute",
    network=network,
    storage=storage,
    ecr=ecr_stack,
    env=env,
)

app.synth()
