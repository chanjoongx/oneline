# web, the Oneline control surface

The Oneline control surface: the dashboard plus the Cloud Run deploy client.
Dark, landscape, built on the shared design tokens so it looks like the same
product as the tools it makes.

## What it shows

- A single input for the spoken need at the top.
- Three candidate columns that fill in real time over Server-Sent Events, each
  with a live status bar, a code preview, and per-candidate judge scores. The
  winner is highlighted. The parallel build is visible: three sandboxes work at
  once and finish independently.
- A split result area once a winner is selected:
  - Left half: the QR code rendered large, an open link button, and the live
    Cloud Run URL in mono beneath as a fallback if scanning is slow.
  - Right half: a phone mockup with an iframe preview of the winning tool that
    renders instantly from the HTML string, before and independent of Cloud Run.
    The device keeps a realistic 9 to 19.5 portrait aspect ratio, sits with
    margin above and below, is centered, and never stretches to fill the panel.
- A knowledge base panel that grows when a build adds lessons, lists the lessons
  applied to the current build, and reports the repeat-failures metric. The
  loop is visible: run a second request and the count climbs.

## Run

```bash
cd web
npm install
npm run dev
# open http://localhost:3000
```

By default the dashboard runs a self-contained engine that produces the same
event shapes a live core run produces, with the deploy simulated so it works
fully offline. The three columns, the split result, the phone mockup, and the
learning loop all work with no external services.

## Live Cloud Run deploy

Turn on the real deploy:

```bash
ONELINE_DEPLOY_REAL=1 npm run dev
```

With the real path on, the dashboard pushes the winning tool to the next
pre-warmed service in the pool and renders the QR from the live URL. If the
deploy is slow or fails, the QR falls back to a pre-deployed URL and the iframe
preview still shows the result, so the demo never stalls.

Pre-provision the pool first (once gcloud is authenticated):

```bash
python scripts/prewarm.py
```

Environment overrides: `ONELINE_REGION` (default us-west2), `ONELINE_PROJECT`
(your GCP project), `ONELINE_FALLBACK_URL`, `ONELINE_DEPLOY_DRYRUN=1`
to force the simulated deploy, `PYTHON` to point at a specific interpreter.

## The deploy client

`deployer.py` is the canonical deploy path and implements the Deployer Protocol
from `core/interfaces.py`:

```python
from web.deployer import CloudRunDeployer
from core import orchestrator

deps = orchestrator.make_default_deps(deployer=CloudRunDeployer())
result = orchestrator.run(need, deps)
```

It writes a BOM-free Dockerfile (`python:3.12-slim`, served on port 8080),
deploys from source, rotates services oneline-demo-1..5, retries past a failing
service, and returns `{ "url", "service", "ts" }`. The dashboard calls the same
file as a subprocess, so core and the dashboard share one tested path.

## Contract

The dashboard renders the shared shapes (Candidate, JudgeScores, Selection,
Lesson) and the orchestrator run result. The TypeScript mirrors live in
`lib/types.ts` and track `shared/schemas`. The web code never edits `shared/`;
shape changes happen in `shared/` first.

## Layout

```
web/
  app/
    layout.tsx, page.tsx, globals.css
    api/run/route.ts     SSE pipeline stream
    api/kb/route.ts      seed knowledge base, read only
  components/            dashboard, columns, result split, phone, QR, kb panel
  lib/
    types.ts             shared shape mirrors
    events.ts            SSE event protocol
    demoEngine.ts        pipeline driver, schema accurate
    deployClient.ts      server side deploy invocation, simulate or real
    kb.ts                seed reader
    useRun.ts            client hook, SSE consumer, localStorage kb state
    fixtures/            working single-file tools (timer, flashcards, ...)
  deployer.py            canonical Cloud Run deploy client and Protocol impl
  scripts/prewarm.py     pre-provision the pool
```
