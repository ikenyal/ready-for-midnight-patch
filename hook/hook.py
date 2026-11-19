"""Server-side layer (L3): a before_tool_call lifecycle hook on the harness.

It runs inside AWS, before the harness hands any tool call to the client. Even a client without the
gate (a bug, an old script, a different machine) cannot receive a call that breaks these checks.
A deny skips the call; the model sees that it did not happen.
"""
import json

ALLOWED = {
    "inventory": {"env"},
    "snapshot_dev": {"label"},
    "upgrade_dev_php": {"version"},
    "check_dev_pages": {"paths"},
    "propose_prod_change": {"php_version", "summary"},
}
PHP = {"8.2", "8.3"}


def deny(reason):
    return {"decision": "deny", "reason": reason}


def lambda_handler(event, _context):
    if event.get("event") != "before_tool_call":
        return {"decision": "allow"}
    c = event.get("context", {})
    name, kind, args = c.get("toolName"), c.get("toolType"), c.get("toolInput")
    if kind != "inline_function" or name not in ALLOWED:
        return deny(f"R1: tool {name!r} ({kind}) is not on the allowlist")
    if not isinstance(args, dict) or args.get("truncated"):
        return deny("R1: tool input missing or truncated")
    if set(args) - ALLOWED[name]:
        return deny(f"R1: unexpected arguments {sorted(set(args) - ALLOWED[name])}")
    if name == "inventory" and args.get("env") not in ("dev", "prod"):
        return deny("R1: env must be dev or prod")
    if name in ("upgrade_dev_php", "propose_prod_change"):
        v = args.get("version", args.get("php_version"))
        if v not in PHP:
            return deny(f"R1: PHP version must be one of {sorted(PHP)}")
    if name == "snapshot_dev" and "prod" in json.dumps(args).lower():
        return deny("R1: snapshot_dev is for dev only")
    if name == "check_dev_pages":
        p = args.get("paths")
        if not isinstance(p, list) or not 0 < len(p) <= 10 or not all(isinstance(x, str) and x.startswith("/") for x in p):
            return deny("R5: paths must be 1-10 site paths")
    return {"decision": "allow"}
