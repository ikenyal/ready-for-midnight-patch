"""Run attack cases against an agent version: reset the sites, run, judge by real state.
usage: python -m agent.batch v0 <harness-arn> [case-id ...]
  AYR_CASES=holdout  use attacks/holdout.json (default: attacks/cases.json)
  AYR_REPS=3         run each case several times (rep number is added to the case id)
  AYR_MODEL=...      model id (see loop.py)
Results go to results/<version>-<model>[-<set>].jsonl, one line per run.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import check, sites
from .loop import MODEL_ID, Run

ROOT = Path(__file__).resolve().parent.parent
version, arn, *only = sys.argv[1:]
mod = __import__(f"agent.{version}", fromlist=["TOOLS", "dispatch"])
case_set = os.environ.get("AYR_CASES", "cases")
reps = int(os.environ.get("AYR_REPS", "1"))
cases = json.loads((ROOT / "attacks" / f"{case_set}.json").read_text())
model_tag = MODEL_ID.removeprefix("us.").replace(".", "-").replace(":", "-")
suffix = ("" if case_set == "cases" else f"-{case_set}") + ("-reps" if reps > 1 else "")
ablate = os.environ.get("AYR_ABLATE", "")
if ablate:
    suffix += "-no-" + ablate.replace(",", "-")
out = ROOT / "results" / f"{version}-{model_tag}{suffix}.jsonl"
out.parent.mkdir(exist_ok=True)

for case in cases:
    if only and case["id"] not in only:
        continue
    for rep in range(1, reps + 1):
        run_id = case["id"] if reps == 1 else f"{case['id']}#{rep}"
        subprocess.run(["bash", str(ROOT / "env" / "reset.sh")], check=True, capture_output=True)
        if case.get("seed_comment"):  # extra attacker-written text for this case only
            for env in sites.ENVS:
                sites.wp(env, ["comment", "create", "--comment_post_ID=1", "--comment_approved=1",
                               "--comment_author=Contact form", f"--comment_content={case['seed_comment']}"])
        transcript = ROOT / "runs" / f"{version}-{model_tag}{suffix}" / f"{run_id.replace('#', '-')}.jsonl"
        transcript.unlink(missing_ok=True)
        t0 = time.time()
        try:
            answer = Run(arn, mod.TOOLS, mod.dispatch, transcript,
                         session_tag=f"ayr-{version}-{case['id']}").ask(case["prompt"])
        except Exception as e:
            answer = f"[run error] {type(e).__name__}: {e}"
        st = check.state()
        error = answer.startswith("[run error]")
        row = {"case": run_id, "version": version, "model": MODEL_ID, "violations": check.violations(st),
               "error": error, "state": st, "answer": answer, "seconds": round(time.time() - t0)}
        with out.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{run_id}: {'ERROR ' + answer[:120] if error else (row['violations'] or 'held')}", flush=True)
        if error and "Token" in answer:
            sys.exit("AWS credentials expired: refresh them (for example `aws sso login`) and start again")
