# Pattern: inline functions with a gate, on the AgentCore managed harness

Use this when an agent on the AgentCore managed harness must act on systems you control, and some actions must
never happen whatever the model is told. The model proposes tool calls; your code decides, from the real state,
whether each one runs.

Code: `agent/loop.py` (client loop), `agent/gate.py` (checks), `hook/hook.py` (server-side hook).

## The shape

1. Define each action as an **inline function** with a narrow schema (`additionalProperties: false`, enums for
   anything that can be an enum). Do not give a tool a free-form target like `env` if only one target is allowed:
   name the target in the tool (`snapshot_dev`, not `snapshot(env)`).
2. List only those tools in **`allowedTools`**, with the `@*/name` selector.
3. When the stream ends with `stopReason: tool_use`, run each requested tool **through your gate**, which checks
   the real state before acting and returns `DENIED (<rule>): <why>` as the tool result when a check fails.
4. Optionally add a **`before_tool_call` hook** (Lambda) that re-checks names and arguments inside AWS.
5. Return results that are **facts, not text from the outside world** (status codes, categories, identifiers).

## Where you will trip

- **Plain names in `allowedTools` hide inline functions.** `["inventory"]` matched nothing the model could see;
  `["@*/inventory"]` works and keeps built-in shell/file tools out.
- **Several tool calls in one response.** Send back every `toolUse` (as an assistant message) and every
  `toolResult` (as one user message) in a single follow-up. Missing one fails with
  `Inline function result is missing toolUseId`.
- **The harness does not keep an unanswered inline call.** The follow-up must include the assistant `toolUse`
  blocks, not just your results.
- **A call denied by the hook still appears in the stream** as a `toolUse` block, followed by a `hookEvent` with
  `decision: deny`. Match decisions to calls (oldest call without a decision) and never run a denied call.
- **Long answers end the stream with an error** (`maximum token limit`). Pass `maxTokens` per invocation.
- **Judge by state, not by the agent's words**, and record run errors separately. A failed run changes nothing,
  so a state-only check will report it as "held".

## Minimal loop

```python
r = client.invoke_harness(harnessArn=arn, runtimeSessionId=session, tools=TOOLS,
                          allowedTools=[f"@*/{t['name']}" for t in TOOLS], maxTokens=8000, messages=messages)
uses, stop = read_stream(r["stream"])          # collect toolUse blocks; drop ones a hook denied
if stop == "tool_use":
    calls, results = [], []
    for u in uses:
        out = gate_and_run(u["name"], u["input"])   # returns "DENIED (...)" instead of acting
        calls.append({"toolUse": {"toolUseId": u["id"], "name": u["name"], "input": u["input"]}})
        results.append({"toolResult": {"toolUseId": u["id"], "content": [{"text": out}], "status": "success"}})
    messages = [{"role": "assistant", "content": calls}, {"role": "user", "content": results}]
```

The full version, with transcript recording for replay, is `agent/loop.py`.
