"""Diagnostic: does the model see the inline tools?  usage: python -m agent.diag <arn> <allowed-json>"""
import json
import sys
import uuid

import boto3

from . import v0
from .loop import MODEL_ID, REGION

arn, allowed = sys.argv[1], json.loads(sys.argv[2])
c = boto3.Session(profile_name="brightflow-sandbox-ikeda", region_name=REGION).client("bedrock-agentcore")
kw = {"allowedTools": allowed} if allowed is not None else {}
r = c.invoke_harness(harnessArn=arn, runtimeSessionId=f"diag-{uuid.uuid4().hex}", tools=v0.TOOLS,
                     model={"bedrockModelConfig": {"modelId": MODEL_ID}}, **kw,
                     messages=[{"role": "user", "content": [{"text": "List the names of the tools you can call. Then call fetch with env=dev and path=/."}]}])
for ev in r["stream"]:
    k = next(iter(ev))
    if k in ("contentBlockStart", "messageStop", "runtimeClientError", "hookEvent"):
        print(k, json.dumps(ev[k])[:300])
    elif k == "contentBlockDelta" and "text" in ev[k].get("delta", {}):
        print(ev[k]["delta"]["text"], end="")
