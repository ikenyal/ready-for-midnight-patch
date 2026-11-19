"""Human step: apply the newest production plan after checking it again.  usage: python -m agent.approve
The agent has no tool that reaches this code. A person runs it."""
import json
import sys

from . import gate, sites

plans = sorted(gate.PLANS.glob("prod-php-*.json"))
if not plans:
    sys.exit("no plan waiting")
plan = json.loads(plans[-1].read_text())
print(json.dumps(plan, indent=2))
v = plan["php_version"]
# Re-check at approval time: the plan may be stale.
gate.require(sites.php_version("dev").startswith(v), "R2", f"dev is no longer on PHP {v}")
pages = json.loads(gate.check_dev_pages(["/", "/?p=1"]))["pages"]
gate.require(all(p["error"] is None for p in pages), "R2", "dev pages are failing now")
if input(f"Apply PHP {v} to PROD? Type 'apply prod' to continue: ").strip() != "apply prod":
    sys.exit("not applied")
print(sites.snapshot("prod", f"before-php-{v}"))
print(sites.set_php("prod", v))
print("prod PHP:", sites.php_version("prod"))
