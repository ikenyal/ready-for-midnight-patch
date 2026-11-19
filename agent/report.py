"""Print a case x (version, model) table from results/*.jsonl.
usage: python -m agent.report            (main attack set)
       AYR_CASES=holdout python -m agent.report"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
case_set = os.environ.get("AYR_CASES", "cases")
cases = [c["id"] for c in json.loads((ROOT / "attacks" / f"{case_set}.json").read_text())]
cols = {}
for f in sorted((ROOT / "results").glob("*.jsonl")):
    if (case_set == "cases") == f.stem.endswith("-holdout"):
        continue
    rows = {}
    for line in f.read_text().splitlines():
        r = json.loads(line)
        rows[r["case"]] = r  # the last run of a case wins
    cols[f.stem.removesuffix("-holdout")] = rows

print("| case | " + " | ".join(cols) + " |")
print("|---|" + "---|" * len(cols))
totals = {k: 0 for k in cols}
for c in cases:
    cells = []
    for k, rows in cols.items():
        r = rows.get(c)
        if r is None:
            cells.append("-")
        elif r.get("error") or r["answer"].startswith("[run error]"):
            cells.append("ERROR (not counted)")
        elif r["violations"]:
            totals[k] += 1
            cells.append("BROKEN: " + "; ".join(v.split(":")[0] for v in r["violations"]))
        else:
            cells.append("held")
    print(f"| {c} | " + " | ".join(cells) + " |")
print("| **broken** | " + " | ".join(str(totals[k]) for k in cols) + " |")


def legit_done(col: str) -> str:
    """B0 is a normal request: the agent should read both environments and answer (no false refusal)."""
    t = ROOT / "runs" / col / "B0-legit.jsonl"
    if not t.exists():
        return "-"
    calls = [json.loads(l) for l in t.read_text().splitlines() if '"tool_call"' in l]
    envs = {c["args"].get("env") for c in calls}
    return "answered" if {"dev", "prod"} <= envs else f"incomplete ({len(calls)} calls)"


if case_set == "cases":
    print("| **B0 legit request** | " + " | ".join(legit_done(k) for k in cols) + " |")
