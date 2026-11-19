"""Run every attack case against an agent version: reset the sites, run, judge by real state.
usage: python -m agent.batch v0 <harness-arn> [case-id ...]
Results go to results/<version>.jsonl (one line per case).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from . import check
from .loop import MODEL_ID, Run

ROOT = Path(__file__).resolve().parent.parent
version, arn, *only = sys.argv[1:]
mod = __import__(f"agent.{version}", fromlist=["TOOLS", "dispatch"])
cases = json.loads((ROOT / "attacks" / "cases.json").read_text())
model_tag = MODEL_ID.removeprefix("us.").replace(".", "-").replace(":", "-")
out = ROOT / "results" / f"{version}-{model_tag}.jsonl"
out.parent.mkdir(exist_ok=True)

for case in cases:
    if only and case["id"] not in only:
        continue
    subprocess.run(["bash", str(ROOT / "env" / "reset.sh")], check=True, capture_output=True)
    transcript = ROOT / "runs" / f"{version}-{model_tag}" / f"{case['id']}.jsonl"
    transcript.unlink(missing_ok=True)
    t0 = time.time()
    try:
        answer = Run(arn, mod.TOOLS, mod.dispatch, transcript, session_tag=f"ayr-{version}-{case['id']}").ask(case["prompt"])
    except Exception as e:
        answer = f"[run error] {type(e).__name__}: {e}"
    st = check.state()
    row = {"case": case["id"], "version": version, "violations": check.violations(st), "state": st,
           "answer": answer, "seconds": round(time.time() - t0)}
    with out.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{case['id']}: {row['violations'] or 'held'}", flush=True)
