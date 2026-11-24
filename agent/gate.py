"""The gate: every v1 tool call passes through here before anything touches a site.

The model never decides whether an action is allowed. This code does, from the real state of the sites.
"""
import json
import os
import re
import time
from pathlib import Path

from . import sites

ALLOWED_PHP = {"8.2", "8.3"}
SNAPSHOT_MAX_AGE = 24 * 3600
PLANS = Path(__file__).resolve().parent.parent / "plans"
# Ablation switches for measuring what each layer contributes (never set them in real use):
#   AYR_ABLATE=gate     the gate's checks always pass (L2 off)
#   AYR_ABLATE=shaping  page checks also return the page text to the model (L4 off)
ABLATE = set(filter(None, os.environ.get("AYR_ABLATE", "").split(",")))


class Denied(Exception):
    """Raised when a call breaks a rule. The message is returned to the model as the tool result."""


def require(cond: bool, rule: str, why: str):
    if not cond and "gate" not in ABLATE:
        raise Denied(f"DENIED ({rule}): {why}")


def newest_snapshot_age(env: str) -> float | None:
    d = sites.SNAPSHOT_DIR / env
    files = list(d.glob("*.tgz")) if d.exists() else []
    return min(time.time() - f.stat().st_mtime for f in files) if files else None


def check_env(env) -> str:
    require(env in sites.ENVS, "R1", f"unknown environment {env!r}; use 'dev' or 'prod'")
    return env


def check_version(version) -> str:
    require(isinstance(version, str) and version in ALLOWED_PHP, "R1", f"PHP version must be one of {sorted(ALLOWED_PHP)}")
    return version


# ---- tools (each one is the only way the model can reach a site) ----

def inventory(env) -> str:
    """Read-only. Structured facts only; no free text from the site."""
    env = check_env(env)
    plugins = json.loads(sites.wp(env, ["plugin", "list", "--fields=name,status,version", "--format=json"]) or "[]")
    return json.dumps({"env": env, "wordpress": sites.wp(env, ["core", "version"]).strip()[:20],
                       "php": sites.php_version(env)[:20],
                       "plugins": [{k: str(p[k])[:60] for k in ("name", "status", "version")} for p in plugins]})


def snapshot_dev(label) -> str:
    """R3: the only snapshot tool, and it only targets dev."""
    return sites.snapshot("dev", str(label))


def upgrade_dev_php(version) -> str:
    """R1 + R3: only dev, only allowed versions, only with a fresh snapshot."""
    version = check_version(version)
    age = newest_snapshot_age("dev")
    require(age is not None and age < SNAPSHOT_MAX_AGE, "R3", "take a dev snapshot first (none in the last 24h)")
    sites.set_php("dev", version)
    return json.dumps({"env": "dev", "php": sites.php_version("dev")[:20]})


def check_dev_pages(paths) -> str:
    """R5: return status codes and error categories, never the page text.
    If an error names an installed plugin, return only that plugin's slug."""
    require(isinstance(paths, list) and 0 < len(paths) <= 10, "R5", "paths must be a list of 1-10 site paths")
    slugs = [p["name"] for p in json.loads(sites.wp("dev", ["plugin", "list", "--fields=name", "--format=json"]) or "[]")]
    out = []
    for path in paths:
        require(isinstance(path, str) and re.fullmatch(r"/[\w\-./?=&%]*", path) is not None, "R5", f"bad path {path!r}")
        status, text = sites.fetch("dev", path)
        fatal = bool(re.search(r"\bFatal error\b", text))
        named = [s for s in slugs if fatal and s in text]
        php_error = None
        if status >= 500:
            # WordPress often shows only a generic "critical error" page. Read PHP's own log line, and pass on
            # only structured facts from it: the plugin directory in the file path, and the error kind.
            line = sites.last_php_fatal("dev")
            m = re.search(r"/wp-content/plugins/([a-z0-9\-]+)/", line)
            if m and m.group(1) in slugs and m.group(1) not in named:
                named.append(m.group(1))
            u = re.search(r"Call to undefined function (\w+)\(\)", line)
            php_error = {"kind": "undefined_function", "function": u.group(1)} if u else ("fatal" if line else None)
            fatal = fatal or bool(line)
        out.append({"path": path, "status": status,
                    "error": "php_fatal" if fatal else ("http_error" if status >= 400 else None),
                    "plugins_named_in_error": named, "php_error": php_error})
        if "shaping" in ABLATE:
            out[-1]["text"] = text[:3000]
    return json.dumps({"env": "dev", "pages": out})


def propose_prod_change(php_version, summary) -> str:
    """R2 + R7: the agent's only way toward prod. Writes a plan for a human; changes nothing.
    The plan is accepted only if dev already runs that version and its pages are healthy."""
    php_version = check_version(php_version)
    require(sites.php_version("dev").startswith(php_version), "R2", f"dev is not on PHP {php_version} yet")
    pages = json.loads(check_dev_pages(["/", "/?p=1"]))["pages"]
    require(all(p["error"] is None for p in pages), "R2", "dev pages are failing; fix or report before proposing prod")
    PLANS.mkdir(exist_ok=True)
    plan = {"created": time.time(), "php_version": php_version, "summary": str(summary)[:2000],
            "prod_settings": "unchanged (R7: keep prod's current values)", "dev_pages": pages}
    path = PLANS / f"prod-php-{php_version}-{int(time.time())}.json"
    path.write_text(json.dumps(plan, indent=2))
    return json.dumps({"plan": path.name, "status": "waiting for human approval (apply with: python -m agent.approve)"})
