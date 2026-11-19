"""Run one task against an agent version and record the transcript.
usage: python -m agent.run v0 <harness-arn> <case-name> "<prompt>"
"""
import sys
from pathlib import Path

from .loop import Run

version, arn, case, prompt = sys.argv[1:5]
mod = __import__(f"agent.{version}", fromlist=["TOOLS", "dispatch"])
out = Path(__file__).resolve().parent.parent / "runs" / version / f"{case}.jsonl"
out.unlink(missing_ok=True)
answer = Run(arn, mod.TOOLS, mod.dispatch, out, session_tag=f"ayr-{version}-{case}").ask(prompt)
print(answer)
print(f"\n[transcript] {out}")
