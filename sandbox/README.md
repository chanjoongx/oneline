# sandbox: the Managed Agents integration

This package is the heart of Oneline. It builds each candidate tool inside its
own Gemini Managed Agents sandbox, then hands the sandbox id to the functionality
judge so Playwright tests run in the very sandbox that built the tool. Build,
test, and verification all live inside managed sandboxes, three in parallel.

## What it does

1. Assembles the implementer prompt for a candidate (three strategy variants:
   A speed_minimal, B polish, C minimal_whitespace). All three inline
   `shared/base.css` verbatim, set exactly one accent from the six approved
   hexes, and obey the shared design system (`shared/base.css`). They differ only in
   layout, interaction structure, and density, never in palette or typography.
   A scope lock restates the plan's core interactions and forbids anything not on
   that list, so tools stay minimal and small (no surprise extras, less bloat).
2. Spawns one isolated managed sandbox per candidate and runs the prompt with
   `gemini-3.5-flash` inside it.
3. Extracts the single-file HTML, guarantees no em dash, resolves the accent, and
   returns a `Candidate` that matches `shared/schemas/candidate.schema.json`.
4. Exposes each candidate's `environment_id` so the functionality judge reuses
   the same sandbox.

## The Managed Agents call (settled shape)

Confirmed working against the live API (google-genai upgraded):

```python
from google import genai
client = genai.Client(api_key=...)            # GEMINI_API_KEY from env

interaction = client.interactions.create(
    agent="antigravity-preview-05-2026",
    input=prompt,                              # the implementer prompt
    environment="remote",                      # spawns a fresh isolated sandbox
)

interaction.output_text      # model output (HTML block + Rationale line)
interaction.id               # interaction id
interaction.environment_id   # the sandbox id, reused by the functionality judge
interaction.steps            # agent steps taken
```

Reuse a sandbox by passing the saved id as `environment` (confirmed against the
quickstart "Continue the conversation" section and the agent-environment doc):

```python
client.interactions.create(
    agent="antigravity-preview-05-2026",
    environment=environment_id,            # the existing sandbox, by id
    previous_interaction_id=interaction.id,  # optional continuity hint
    input="Run this command and report stdout, stderr, exit code: ...",
)
```

Per the docs, commands and file operations run through the natural-language
`input` (there is no dedicated command, exec, or files parameter). Reuse needs
only the `environment_id` string; `previous_interaction_id` is optional.

`sandbox.client.create_interaction` and `sandbox.client.reuse_environment` wrap
these. `create_interaction` tries `model="gemini-3.5-flash"` and falls back by
dropping optional kwargs the SDK does not accept (model, previous_interaction_id)
so the call works across SDK builds; the managed agent is configured for
gemini-3.5-flash either way.

## Running a command in the candidate's sandbox

The functionality judge reuses the candidate's `environment_id` to run its tests
in the same sandbox that built the tool. Use the clean helper:

```python
from sandbox import run_in_existing_environment

interaction = run_in_existing_environment(
    candidate["environment_id"],
    "python /work/test.py",            # the command to run
    client,                            # your google-genai client (or omit to build one)
    previous_interaction_id=None,      # optional, if you have the build interaction id
)
text = interaction.output_text         # parse STDOUT / STDERR / EXIT_CODE from here
```

Output contract with `report=True` (default), so `output_text` is parseable:

```
STDOUT:
<the full standard output>
STDERR:
<the full standard error>
EXIT_CODE: <integer exit code>
```

For multi-step work (write tool.html, write a test, then run it) use the
lower-level `reuse_environment(environment_id, prompt, client)`, which sends a
raw natural-language `input` to the same sandbox. Set `report=False` on
`run_in_existing_environment` to send a raw command without the report wrapper.

Coordination note: the Candidate carries `environment_id` but not the build
`interaction.id` (the shared candidate schema has no field for it), so sandbox
reuse defaults to environment-id-only, which the docs confirm works. If the judge
wants strict conversation continuity via `previous_interaction_id`, the candidate
schema in `shared/` would need an optional `interaction_id` field added.

### Running the functionality test in the candidate's sandbox

One call does the whole flow in the same sandbox that built the candidate: write
the tool HTML (exact bytes via base64), write the test, install Playwright and
Chromium, run the test, and read the screenshot back to confirm capture.

```python
from sandbox import run_functionality_test

result = run_functionality_test(
    candidate["environment_id"],
    candidate["html"],
    test_script,            # omit to use the default smoke test (loads + screenshots)
    client=client,
)
# result = {
#   "environment_id", "exit_code", "stdout", "stderr",
#   "screenshot_path",    # None when the capture did not happen
#   "screenshot_exists", "screenshot_size", "raw",
# }
```

With no `test_script`, the default test loads `file:///work/tool.html` at a 390px
viewport, screenshots to `/work/screenshot.png`, and prints
`RESULT_JSON {...}`; this verifies the file path and the load actually work in the
reused environment. `default_playwright_test(tool_path, screenshot_path)` returns
that script so the functionality judge can extend it.

Lower-level pieces (compose your own flow):

```python
from sandbox import (
    write_file_to_environment, ensure_playwright_in_environment,
    run_in_existing_environment, read_file_from_environment,
    parse_run_report, parse_file_report,
)
from sandbox.config import DEFAULT_TOOL_PATH, DEFAULT_SCREENSHOT_PATH

env = candidate["environment_id"]
write_file_to_environment(env, DEFAULT_TOOL_PATH, candidate["html"], client)  # base64, exact bytes
write_file_to_environment(env, "/work/test.py", test_script, client)
ensure_playwright_in_environment(env, client)                                 # pip + chromium
run = run_in_existing_environment(env, "python /work/test.py", client)        # STDOUT/STDERR/EXIT_CODE
report = parse_run_report(run.output_text)                                    # {stdout, stderr, exit_code}

shot = read_file_from_environment(env, DEFAULT_SCREENSHOT_PATH, client)       # FILE/EXISTS/SIZE
parse_file_report(shot.output_text)                                          # {path, exists, size, base64}
```

Notes for the functionality judge:
- Files are written by base64 so the HTML lands byte for byte, no escaping or
  agent edits. `write_file_to_environment` accepts str or bytes.
- Have the test save the screenshot inside a try/finally so it is written even on
  an assertion failure. `EXISTS: false` or `SIZE: 0` from the read tells you the
  capture step failed rather than passing a silent `screenshot=null`.
- The viewport is 390px wide. Use a JPEG (or clip) to keep the base64 small if you
  pull the image with `include_contents=True`.

## Completeness and truncation guard

Larger tools were being truncated mid-script at the default output token cap. Two
defences:

- The output cap is raised on every `interactions.create` call
  (`config.MAX_OUTPUT_TOKENS`, default 32768, env `ONELINE_MAX_OUTPUT_TOKENS`), so
  a complete self-contained tool fits. `extract_html` also recovers the partial
  body from an unclosed code fence instead of returning the fence wrapper.
- Before a Candidate is returned, `extract.html_problems` checks the HTML is
  structurally complete (closing `</script>`, `</body>`, `</html>`, balanced
  `<style>`). On a truncated result the build retries up to `max_build_attempts`
  (default 2); if it still does not complete, `IncompleteHTMLError` is raised so a
  broken tool is never passed on. `is_html_complete(html)` is exported for reuse.

## Integration with core

`ManagedAgentsImplementer` implements the `ImplementerClient` Protocol in
`core/interfaces.py`. core injects it:

```python
from sandbox import ManagedAgentsImplementer
from core import orchestrator

deps = orchestrator.make_default_deps(implementer=ManagedAgentsImplementer())
orchestrator.run("a tap counter I reset each day", deps)
```

- `build_candidate(strategy, brief, lessons) -> Candidate` builds one candidate
  in its own sandbox. This is the Protocol method core calls today.
- `build_candidates(strategies, brief, lessons) -> list[Candidate]` spawns the
  three sandboxes in parallel (one thread per candidate) and returns them in
  order. core can adopt this in place of its per-strategy loop, or wrap each
  `build_candidate` call in a ParallelAgent. Either way the three managed
  sandboxes run concurrently.

## Hard rules enforced here

- Build only what the plan asked for. The scope lock restates the plan's core
  interactions and forbids any extra button, control, export, copy, share, or
  summary. This keeps tools minimal and small enough to avoid truncation.
- Generated tools call nothing at runtime except optionally a CDN font. No
  backend, no auth, no remote fetch. The prompt forbids loading Tailwind or any
  framework; output is one self-contained HTML file with inline CSS and JS.
- No em dashes anywhere. The prompt forbids them, and `extract.assert_no_em_dash`
  is the last line of defence: every Candidate is verified and sanitized before
  it leaves this package.
- One accent per tool from the approved six. `accents.recommend_accent` picks a
  sensible default per category; the accent the model actually wrote wins if it
  is on-system, otherwise the recommendation is used. The result is always a
  valid approved hex.

## Run it

```bash
python -m sandbox.test_sandbox            # offline tests, no API key
python -m sandbox.demo --offline          # build one candidate offline
python -m sandbox.demo --offline --parallel   # build three in parallel offline
python -m sandbox.demo --parallel --need "interval timer for boxing rounds" --category timer
                                          # live, needs GEMINI_API_KEY
```

`sandbox.fake.FakeManagedClient` is an offline stand-in for the managed client
(used by the tests and `--offline`); it is also handy for local web and judge
development without spending credits. It is never used on the live path.

## Files

| File | Role |
|---|---|
| `implementer.py` | `ManagedAgentsImplementer`: build_candidate, parallel build_candidates, completeness guard, IncompleteHTMLError |
| `client.py` | Managed Agents wrapper: create_interaction (raised output cap), reuse_environment, run_in_existing_environment, write_file_to_environment (base64), ensure_playwright_in_environment, run_functionality_test, parse_run_report, parse_file_report |
| `prompts.py` | implementer prompt assembly, scope lock, three strategy variants, base.css inlining |
| `accents.py` | accent recommendation and normalization, approved set only |
| `extract.py` | HTML and rationale extraction, accent parsing, em dash verification, completeness checks |
| `config.py` | agent name, model, output cap, sandbox paths, approved accents, api key reader |
| `fake.py` | offline managed-client stand-in |
| `demo.py` | end-to-end CLI |
| `test_sandbox.py` | offline tests |
