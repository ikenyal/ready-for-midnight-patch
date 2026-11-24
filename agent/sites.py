"""Thin access layer to the two local WordPress sites (dev and prod) run by env/compose.yaml.

This module performs real actions and contains no rule checks.
v0 calls it directly; v1 reaches it only through the gate.
"""
import html
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ENVS = {"dev": 18081, "prod": 18082}
PHP_TAGS = {"7.4": "6-php7.4-apache", "8.1": "6-php8.1-apache", "8.2": "6-php8.2-apache", "8.3": "6-php8.3-apache"}
COMPOSE_DIR = Path(__file__).resolve().parent.parent / "env"


def _sh(args: list[str], timeout: int = 300) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout + p.stderr).strip()
    return out if p.returncode == 0 else f"[exit {p.returncode}] {out}"


def shell(env: str, command: str) -> str:
    """Run a shell command inside the site's web container."""
    return _sh(["podman", "exec", f"ayr_{env}-wp_1", "bash", "-lc", command])


def wp(env: str, args: list[str]) -> str:
    """Run wp-cli against the site. Plugins and themes are not loaded (--skip-plugins --skip-themes), so wp-cli
    keeps working on a site that a broken plugin has taken down — as an operator would run it."""
    return _sh([
        "podman", "run", "--rm", "--network", "ayr_default", "--volumes-from", f"ayr_{env}-wp_1",
        "--user", "33:33", "-e", f"WORDPRESS_DB_HOST={env}-db", "-e", "WORDPRESS_DB_USER=wp",
        "-e", "WORDPRESS_DB_PASSWORD=wp", "-e", "WORDPRESS_DB_NAME=wp",
        "docker.io/library/wordpress:cli", "wp", "--skip-plugins", "--skip-themes", *args,
    ])


def activate_without_loading(env: str, plugin_file: str) -> str:
    """Mark a plugin active without running it (an old plugin may not even load under wp-cli's PHP)."""
    code = (f"$a = get_option('active_plugins', []); if (!in_array('{plugin_file}', $a)) {{ $a[] = '{plugin_file}'; "
            f"update_option('active_plugins', $a); }} echo 'active';")
    return wp(env, ["eval", code])


def php_version(env: str) -> str:
    return shell(env, "php -r 'echo PHP_VERSION;'")


def set_php(env: str, version: str) -> str:
    """Switch PHP by recreating the site's web container on another image tag (files and DB are kept)."""
    tag = PHP_TAGS[version]
    var = "DEV_PHP_TAG" if env == "dev" else "PROD_PHP_TAG"
    cmd = f"cd '{COMPOSE_DIR}' && {var}={tag} uvx podman-compose up -d --no-deps {env}-wp"
    return _sh(["bash", "-lc", cmd], timeout=900)


SNAPSHOT_DIR = COMPOSE_DIR / "snapshots"


def snapshots(env: str) -> list[str]:
    d = SNAPSHOT_DIR / env
    return sorted(p.name for p in d.glob("*.tgz")) if d.exists() else []


def snapshot(env: str, label: str) -> str:
    """Archive the site's files and a DB dump, and copy the archive out to the host.
    (Kept outside the container: switching PHP recreates the container.)"""
    label = "".join(ch for ch in label if ch.isalnum() or ch in "-_.")[:60] or "snapshot"
    dump = wp(env, ["db", "export", "/var/www/html/.snapshot-db.sql"])
    tar = shell(env, f"tar czf /tmp/{label}.tgz -C /var/www/html . && rm -f /var/www/html/.snapshot-db.sql")
    (SNAPSHOT_DIR / env).mkdir(parents=True, exist_ok=True)
    cp = _sh(["podman", "cp", f"ayr_{env}-wp_1:/tmp/{label}.tgz", str(SNAPSHOT_DIR / env / f"{label}.tgz")])
    return f"{dump}\n{tar}\n{cp}\nsaved: {env}/{label}.tgz"


def fetch(env: str, path: str = "/") -> tuple[int, str]:
    """GET a page. Returns (HTTP status, visible text)."""
    url = f"http://localhost:{ENVS[env]}{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode("utf-8", "replace"), e.code
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return status, re.sub(r"\s+", " ", text).strip()


def last_php_fatal(env: str, since: str = "10m") -> str:
    """The newest 'PHP Fatal error' line from the web container's log (PHP logs to stderr in this image)."""
    out = _sh(["podman", "logs", "--since", since, f"ayr_{env}-wp_1"])
    fatals = [line for line in out.splitlines() if "PHP Fatal error" in line]
    return fatals[-1] if fatals else ""
