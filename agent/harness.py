"""Create the harness for an agent version.  usage: python -m agent.harness v0|v1

Environment:
  AWS_PROFILE    profile to use (optional)
  AYR_ROLE_NAME  harness execution role name (default: agents-your-rules-harness-role)
  AYR_HOOK_ARN   Lambda ARN of the before_tool_call hook; attached to v1 only (see hook/README.md)
"""
import os
import sys
import time

import boto3

from .loop import MODEL_ID, REGION


def create(version: str) -> str:
    mod = __import__(f"agent.{version}", fromlist=["SYSTEM_PROMPT", "TOOLS", "TOOL_NAMES"])
    s = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=REGION)
    account = s.client("sts").get_caller_identity()["Account"]
    role = f"arn:aws:iam::{account}:role/{os.environ.get('AYR_ROLE_NAME', 'agents-your-rules-harness-role')}"
    extra = {}
    if version == "v1" and os.environ.get("AYR_HOOK_ARN"):
        extra["hooks"] = [{"beforeToolCall": {"name": "rules_gate", "target": {"lambda": {
            "arn": os.environ["AYR_HOOK_ARN"], "timeoutSeconds": 5, "failureMode": "deny"}}}}]
    c = s.client("bedrock-agentcore-control")
    r = c.create_harness(
        harnessName=f"ayr_{version}", executionRoleArn=role,
        model={"bedrockModelConfig": {"modelId": MODEL_ID}},
        systemPrompt=[{"text": mod.SYSTEM_PROMPT}],
        # Only our inline functions; no built-in shell/files. Plain names only match built-ins,
        # so inline functions need the "@*/name" selector.
        tools=mod.TOOLS, allowedTools=[f"@*/{n}" for n in mod.TOOL_NAMES],
        memory={"disabled": {}}, maxIterations=30, **extra)
    hid = r["harness"]["harnessId"]
    while (h := c.get_harness(harnessId=hid)["harness"])["status"] == "CREATING":
        time.sleep(15)
    print(h["status"], h["arn"])
    return h["arn"]


if __name__ == "__main__":
    create(sys.argv[1])
