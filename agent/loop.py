"""Client-side agent loop for an AgentCore harness with inline function tools.

The harness runs the model loop. When the model calls an inline function, the stream ends with
stopReason=tool_use; we run the tool here and send the toolResult back on the same session.
Every event is appended to a JSONL transcript so a run can be replayed without AWS.
"""
import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable

import boto3

REGION = "us-west-2"
# The harness lets us switch models per invocation; AYR_MODEL picks one for a whole run.
MODEL_ID = os.environ.get("AYR_MODEL", "us.moonshotai.kimi-k3.1")


def new_session_id(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex}"[:100]


class Run:
    def __init__(self, harness_arn: str, tools: list[dict], dispatch: Callable[[str, dict], str],
                 transcript: Path, profile: str | None = os.environ.get("AWS_PROFILE"), session_tag: str = "ayr",
                 system_prompt: str | None = None):
        self.client = boto3.Session(profile_name=profile, region_name=REGION).client("bedrock-agentcore")
        self.arn, self.tools, self.dispatch = harness_arn, tools, dispatch
        # Sent with every call, so the rules in the code are the rules the model sees.
        self.extra = {"systemPrompt": [{"text": system_prompt}]} if system_prompt else {}
        self.session = new_session_id(session_tag)
        self.transcript = transcript
        transcript.parent.mkdir(parents=True, exist_ok=True)

    def log(self, kind: str, **data):
        with self.transcript.open("a") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, **data}, ensure_ascii=False) + "\n")

    def _invoke(self, messages: list[dict]) -> tuple[str, list[dict], str]:
        """One InvokeHarness call. Returns (assistant text, tool uses, stop reason)."""
        r = self.client.invoke_harness(
            harnessArn=self.arn, runtimeSessionId=self.session, tools=self.tools,
            allowedTools=[f"@*/{t['name']}" for t in self.tools], maxTokens=8000, **self.extra,
            model={"bedrockModelConfig": {"modelId": MODEL_ID}}, messages=messages)
        text, uses, cur, stop = [], [], None, None
        for ev in r["stream"]:
            if "contentBlockStart" in ev:
                start = ev["contentBlockStart"].get("start", {})
                if "toolUse" in start:
                    cur = {"toolUseId": start["toolUse"]["toolUseId"], "name": start["toolUse"]["name"], "input": ""}
            elif "contentBlockDelta" in ev:
                d = ev["contentBlockDelta"].get("delta", {})
                if "text" in d:
                    text.append(d["text"])
                elif "toolUse" in d and cur is not None:
                    cur["input"] += d["toolUse"].get("input", "")
            elif "contentBlockStop" in ev and cur is not None:
                uses.append(cur)
                cur = None
            elif "messageStop" in ev:
                stop = ev["messageStop"].get("stopReason")
            elif "hookEvent" in ev:
                h = ev["hookEvent"]
                self.log("hook", event=h)
                # A before_tool_call decision belongs to the oldest tool call that has none yet.
                # A denied call was skipped by the harness and must never be executed here.
                if h.get("type") == "before_tool_call":
                    pending = next((u for u in uses if "decision" not in u), None)
                    if pending is not None:
                        pending["decision"] = h.get("decision")
            elif "runtimeClientError" in ev:
                self.log("error", error=ev["runtimeClientError"])
        uses = [u for u in uses if u.get("decision") != "deny"]
        return "".join(text), uses, stop

    def ask(self, prompt: str, max_turns: int = 25) -> str:
        """Send a user message and keep answering inline tool calls until the agent stops."""
        self.log("user", text=prompt)
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        for _ in range(max_turns):
            text, uses, stop = self._invoke(messages)
            if text:
                self.log("assistant", text=text)
            if stop != "tool_use" or not uses:
                self.log("stop", reason=stop)
                return text
            # The model may request several tools in one response. Run them in order and send every
            # toolUse back with its toolResult (the harness does not persist an unanswered inline call).
            calls, results = [], []
            for use in uses:
                try:
                    args = json.loads(use["input"] or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": use["input"]}
                self.log("tool_call", name=use["name"], args=args, id=use["toolUseId"])
                try:
                    result = self.dispatch(use["name"], args) or "(no output)"  # empty text is rejected by the API
                except Exception as e:  # report tool failures to the model instead of crashing the run
                    result = f"[tool error] {type(e).__name__}: {e}"
                self.log("tool_result", name=use["name"], result=result[:4000], id=use["toolUseId"])
                calls.append({"toolUse": {"toolUseId": use["toolUseId"], "name": use["name"], "input": args}})
                results.append({"toolResult": {"toolUseId": use["toolUseId"],
                                               "content": [{"text": result[:8000]}], "status": "success"}})
            messages = [{"role": "assistant", "content": calls}, {"role": "user", "content": results}]
        self.log("stop", reason="max_turns")
        return text
