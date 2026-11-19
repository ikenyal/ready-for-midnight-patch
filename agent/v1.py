"""v1: the same rules, enforced in layers. Narrow tools, a code gate, no page text to the model, prod by proposal only."""
from . import gate
from .v0 import SYSTEM_PROMPT as _RULES

SYSTEM_PROMPT = _RULES + """

How your tools work: you can read both environments with inventory. You can change dev only, through
snapshot_dev and upgrade_dev_php. check_dev_pages tells you status codes and error categories.
You cannot change prod at all; use propose_prod_change to hand a plan to a human.
If a tool returns DENIED, do not look for a way around it. Report it."""


def _tool(name, desc, props, required):
    return {"type": "inline_function", "name": name, "config": {"inlineFunction": {
        "description": desc, "inputSchema": {"type": "object", "properties": props, "required": required,
                                             "additionalProperties": False}}}}


TOOLS = [
    _tool("inventory", "Read WordPress version, PHP version and plugins of dev or prod.",
          {"env": {"type": "string", "enum": ["dev", "prod"]}}, ["env"]),
    _tool("snapshot_dev", "Archive dev's files and database.", {"label": {"type": "string"}}, ["label"]),
    _tool("upgrade_dev_php", "Switch dev to another PHP version. Needs a fresh dev snapshot.",
          {"version": {"type": "string", "enum": sorted(gate.ALLOWED_PHP)}}, ["version"]),
    _tool("check_dev_pages", "Check dev pages. Returns status codes and error categories only.",
          {"paths": {"type": "array", "items": {"type": "string"}}}, ["paths"]),
    _tool("propose_prod_change", "Write a production change plan for a human to approve. Changes nothing.",
          {"php_version": {"type": "string", "enum": sorted(gate.ALLOWED_PHP)}, "summary": {"type": "string"}},
          ["php_version", "summary"]),
]
TOOL_NAMES = [t["name"] for t in TOOLS]
_IMPL = {n: getattr(gate, n) for n in TOOL_NAMES}


def dispatch(name: str, args: dict) -> str:
    """Unknown tools and unexpected arguments are refused before the gate runs."""
    if name not in _IMPL:
        return f"DENIED (R1): no tool named {name!r}"
    schema = next(t for t in TOOLS if t["name"] == name)["config"]["inlineFunction"]["inputSchema"]
    extra = set(args) - set(schema["properties"])
    if extra:
        return f"DENIED (R1): unexpected arguments {sorted(extra)}"
    try:
        return _IMPL[name](**args)
    except gate.Denied as e:
        return str(e)
    except TypeError as e:
        return f"DENIED (R1): bad arguments ({e})"
