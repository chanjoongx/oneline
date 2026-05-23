"""Cloud Run deploy client for Oneline.

This is the canonical deploy path. It implements the Deployer Protocol from
core/interfaces.py:

    deploy(winner_html: str) -> {"url": str, "service": str, "ts": int}

so it can be injected into the core orchestrator:

    from web.deployer import CloudRunDeployer
    from core import orchestrator
    deps = orchestrator.make_default_deps(deployer=CloudRunDeployer())
    result = orchestrator.run(need, deps)

The Next.js dashboard also calls this file as a subprocess for its own deploy,
so there is one tested deploy path shared by core and the dashboard.

Verified recipe (tested and working):
  - python:3.12-slim base image, served with python -m http.server on PORT 8080.
  - Cloud Run requires port 8080, not 80.
  - The Dockerfile is written as bytes with LF and no BOM. A UTF-8 BOM breaks
    the build, so we never use a writer that prepends one.
  - Region and project come from ONELINE_REGION and ONELINE_PROJECT, with
    gcloud already authenticated.

Resilience:
  - Rotates services oneline-demo-1..5 to avoid stale state and cold starts.
  - On a service failure, rotates to the next service and retries.
  - If every service fails, returns a fallback URL so the demo never stalls.
    The dashboard preview already shows the result, so a degraded deploy still
    leaves a usable result on screen.

No em dashes anywhere. Hyphens only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

POOL = [
    "oneline-demo-1",
    "oneline-demo-2",
    "oneline-demo-3",
    "oneline-demo-4",
    "oneline-demo-5",
]

REGION = os.environ.get("ONELINE_REGION", "us-west2")
PROJECT = os.environ.get("ONELINE_PROJECT", "your-gcp-project")
DEPLOY_TIMEOUT = int(os.environ.get("ONELINE_DEPLOY_TIMEOUT", "300"))
STATE_PATH = Path(__file__).resolve().parent / ".deploy_state.json"

DOCKERFILE_BYTES = (
    b"FROM python:3.12-slim\n"
    b"WORKDIR /app\n"
    b"COPY . /app\n"
    b'CMD ["python","-m","http.server","8080"]\n'
)


def log(msg: str) -> None:
    """Human-readable progress goes to stderr so stdout stays clean JSON."""
    print(msg, file=sys.stderr, flush=True)


def _fallback_url() -> str:
    return os.environ.get("ONELINE_FALLBACK_URL", "https://oneline-demo-1-uc.a.run.app")


def _read_cursor() -> int:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return int(data.get("cursor", 0))
    except Exception:
        return 0


def _write_cursor(cursor: int) -> None:
    try:
        STATE_PATH.write_text(json.dumps({"cursor": cursor}), encoding="utf-8")
    except Exception:
        # Rotation state is best effort. A failed write does not break a deploy.
        pass


def _write_build_dir(html: str) -> str:
    """Stage index.html and a BOM-free Dockerfile in a fresh temp directory."""
    build_dir = tempfile.mkdtemp(prefix="oneline-deploy-")
    # UTF-8 with explicit LF and no BOM.
    with open(os.path.join(build_dir, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    # Dockerfile as raw bytes so nothing can inject a BOM.
    with open(os.path.join(build_dir, "Dockerfile"), "wb") as f:
        f.write(DOCKERFILE_BYTES)
    return build_dir


def _gcloud() -> "str | None":
    return shutil.which("gcloud")


def _deploy_one(gcloud: str, service: str, build_dir: str) -> str:
    """Deploy one service from source. Returns the live URL or raises."""
    cmd = [
        gcloud,
        "run",
        "deploy",
        service,
        "--source",
        build_dir,
        "--region",
        REGION,
        "--project",
        PROJECT,
        "--allow-unauthenticated",
        "--port",
        "8080",
        "--quiet",
        "--format=value(status.url)",
    ]
    log("deploying " + service + " to Cloud Run (" + REGION + ") ...")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=DEPLOY_TIMEOUT)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout or "deploy failed").strip()[:600])
    lines = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError("deploy returned no url")
    return lines[-1]


class CloudRunDeployer:
    """Deployer Protocol implementation. See module docstring."""

    def __init__(self, pool=None, dry_run: "bool | None" = None):
        self.pool = pool or POOL
        if dry_run is None:
            dry_run = os.environ.get("ONELINE_DEPLOY_DRYRUN", "") == "1"
        self.dry_run = dry_run

    def deploy(self, winner_html: str) -> dict:
        ts = int(time.time())

        if self.dry_run:
            cursor = _read_cursor()
            service = self.pool[cursor % len(self.pool)]
            _write_cursor((cursor + 1) % len(self.pool))
            url = "https://" + service + "-uc.a.run.app"
            log("dry run, no gcloud call, returning " + url)
            return {"url": url, "service": service, "ts": ts}

        gcloud = _gcloud()
        if not gcloud:
            log("gcloud not found on PATH, using fallback url")
            return {
                "url": _fallback_url(),
                "service": "fallback",
                "ts": ts,
                "fallback": True,
                "error": "gcloud not found",
            }

        build_dir = _write_build_dir(winner_html)
        cursor = _read_cursor()
        last_error = ""
        # Try services in rotation; move past any that fail.
        for attempt in range(len(self.pool)):
            service = self.pool[(cursor + attempt) % len(self.pool)]
            try:
                url = _deploy_one(gcloud, service, build_dir)
                _write_cursor((cursor + attempt + 1) % len(self.pool))
                log("deployed: " + url)
                return {"url": url, "service": service, "ts": int(time.time())}
            except Exception as e:  # rotate and retry
                last_error = str(e)
                log("service " + service + " failed: " + last_error[:200])

        log("all services failed, using fallback url")
        return {
            "url": _fallback_url(),
            "service": "fallback",
            "ts": int(time.time()),
            "fallback": True,
            "error": last_error[:400],
        }


def _main(argv) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        log('usage: python deployer.py path/to/tool.html [--json] [--dry-run]')
        return 2
    html_path = args[0]
    try:
        html = Path(html_path).read_text(encoding="utf-8")
    except Exception as e:
        log("could not read html: " + str(e))
        return 2

    deployer = CloudRunDeployer(dry_run=("--dry-run" in flags) or None)
    result = deployer.deploy(html)
    # Machine-readable result on stdout (last line) for the dashboard to parse.
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
