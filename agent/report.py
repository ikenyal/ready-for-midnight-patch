"""Print a case x (version, model) table from results/*.jsonl.  usage: python -m agent.report"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cases = [c["id"] for c in json.loads((ROOT / "attacks" / "cases.json").read_text())]
cols = {}
for f in sorted((ROOT / "results").glob("*.jsonl")):
    rows = {}
    for line in f.read_text().splitlines():
        r = json.loads(line)
        rows[r["case"]] = r  # the last run of a case wins
    cols[f.stem] = rows

print("| case | " + " | ".join(cols) + " |")
print("|---|" + "---|" * len(cols))
totals = {k: 0 for k in cols}
for c in cases:
    cells = []
    for k, rows in cols.items():
        r = rows.get(c)
        if r is None:
            cells.append("-")
        elif r["violations"]:
            totals[k] += 1
            cells.append("BROKEN: " + "; ".join(v.split(":")[0] for v in r["violations"]))
        else:
            cells.append("held")
    print(f"| {c} | " + " | ".join(cells) + " |")
print("| **broken** | " + " | ".join(str(totals[k]) for k in cols) + " |")
