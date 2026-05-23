"""Pre-provision the Cloud Run pool before the demo.

Deploys a small placeholder to each service oneline-demo-1..5 with min instances
1 so they stay warm, then the deploy client only swaps content during a run
and returns a live URL fast. Run this once gcloud is authenticated.

    python scripts/prewarm.py

Region defaults to us-west2 and project to a placeholder. Override with
ONELINE_REGION and ONELINE_PROJECT. No em dashes anywhere.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Reuse the verified recipe and pool from the deploy client.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from deployer import DOCKERFILE_BYTES, POOL, PROJECT, REGION  # noqa: E402

PLACEHOLDER = (
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    "<title>Oneline</title>"
    "<style>html,body{margin:0;height:100%;background:#0A0A0B;color:#9A9AA2;"
    "font-family:system-ui,sans-serif;display:flex;align-items:center;"
    "justify-content:center}</style></head><body>ready</body></html>\n"
)


def write_dir() -> str:
    d = tempfile.mkdtemp(prefix="oneline-prewarm-")
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PLACEHOLDER)
    with open(os.path.join(d, "Dockerfile"), "wb") as f:
        f.write(DOCKERFILE_BYTES)
    return d


def main() -> int:
    build_dir = write_dir()
    failures = 0
    for service in POOL:
        cmd = [
            "gcloud", "run", "deploy", service,
            "--source", build_dir,
            "--region", REGION,
            "--project", PROJECT,
            "--allow-unauthenticated",
            "--port", "8080",
            "--min-instances", "1",
            "--memory", "512Mi",
            "--concurrency", "80",
            "--quiet",
            "--format=value(status.url)",
        ]
        print("prewarming " + service + " ...", flush=True)
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            failures += 1
            print("  failed: " + (res.stderr or res.stdout).strip()[:300], flush=True)
        else:
            url = (res.stdout or "").strip().splitlines()[-1]
            print("  ready: " + url, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
