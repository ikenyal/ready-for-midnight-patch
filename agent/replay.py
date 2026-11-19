"""Replay a recorded run without AWS.  usage: python -m agent.replay runs/<dir>/<case>.jsonl [--html out.html]
Shows what the agent was asked, every tool call and result, server-side hook decisions, and its answer."""
import html
import json
import sys
from pathlib import Path

KIND = {"user": "ASK", "assistant": "SAY", "tool_call": "CALL", "tool_result": " ->", "hook": "HOOK", "stop": "END", "error": "ERR"}


def lines(path: Path):
    for raw in path.read_text().splitlines():
        e = json.loads(raw)
        k = e["kind"]
        if k == "tool_call":
            body = f"{e['name']}({json.dumps(e['args'], ensure_ascii=False)})"
        elif k == "tool_result":
            body = e["result"].replace("\n", " ")[:300]
        elif k == "hook":
            ev = e["event"]
            body = f"{ev.get('type')}: {ev.get('decision')} {ev.get('reason', '')}".strip()
        elif k == "stop":
            body = str(e.get("reason"))
        elif k == "error":
            body = json.dumps(e.get("error"))[:300]
        else:
            body = e.get("text", "").strip()
        yield KIND.get(k, k), body


def main():
    path = Path(sys.argv[1])
    rows = list(lines(path))
    if "--html" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--html") + 1])
        color = {"ASK": "#2563eb", "SAY": "#111827", "CALL": "#7c3aed", " ->": "#4b5563", "HOOK": "#b45309", "END": "#6b7280"}
        items = "".join(
            f'<div class="r"><span class="k" style="color:{color.get(k, "#dc2626")}">{html.escape(k)}</span>'
            f'<span class="b{" deny" if "DENIED" in b else ""}">{html.escape(b)}</span></div>' for k, b in rows)
        out.write_text(f"""<!doctype html><meta charset="utf-8"><title>{html.escape(path.stem)}</title>
<style>body{{font:14px/1.45 Menlo,monospace;margin:24px;background:#fff;color:#111}}h1{{font:600 18px Helvetica,Arial}}
.r{{display:flex;gap:12px;margin:4px 0}}.k{{width:48px;flex:none;font-weight:700}}.b{{white-space:pre-wrap;word-break:break-word}}
.deny{{background:#fee2e2;color:#7f1d1d;padding:0 4px;border-radius:4px}}</style>
<h1>{html.escape(path.parent.name)} / {html.escape(path.stem)}</h1>{items}""")
        print(out)
    else:
        for k, b in rows:
            print(f"{k:5} {b}")


if __name__ == "__main__":
    main()
