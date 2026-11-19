"""Create (or show) the harness for an agent version.  usage: python -m agent.harness v0"""
import sys
import time

import boto3

from .loop import MODEL_ID, REGION

ROLE_ARN = "arn:aws:iam::402040564721:role/agents-your-rules-harness-role"


def create(version: str) -> str:
    mod = __import__(f"agent.{version}", fromlist=["SYSTEM_PROMPT", "TOOLS", "TOOL_NAMES"])
    c = boto3.Session(profile_name="brightflow-sandbox-ikeda", region_name=REGION).client("bedrock-agentcore-control")
    r = c.create_harness(
        harnessName=f"ayr_{version}", executionRoleArn=ROLE_ARN,
        model={"bedrockModelConfig": {"modelId": MODEL_ID}},
        systemPrompt=[{"text": mod.SYSTEM_PROMPT}],
        # Only our inline functions; no built-in shell/files. Plain names only match built-ins,
        # so inline functions need the "@*/name" selector (verified 2026-11-19).
        tools=mod.TOOLS, allowedTools=[f"@*/{n}" for n in mod.TOOL_NAMES],
        memory={"disabled": {}}, maxIterations=30)
    hid = r["harness"]["harnessId"]
    while (h := c.get_harness(harnessId=hid)["harness"])["status"] == "CREATING":
        time.sleep(15)
    print(h["status"], h["arn"])
    return h["arn"]


if __name__ == "__main__":
    create(sys.argv[1])
