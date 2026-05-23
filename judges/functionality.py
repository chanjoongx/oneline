"""Functionality judge, deterministic, Playwright in the managed sandbox.

The guiding principle is build and test in the same managed sandbox. The
functionality judge reuses the
candidate's environment_id, the very Gemini Managed Agents sandbox that built the
tool, writes the candidate HTML and a generated Playwright script into it, runs
the script headless, and returns the pass rate, the named passes and failures,
and a screenshot path.

This judge makes no model call. The Playwright script is generated
deterministically from the plan's success_criteria and core_interactions.

There are three pieces:
- generate_playwright_test: builds the headless test script from the plan.
- ManagedAgentsRunner: reuses an existing environment_id to run the test. The
  google-genai SDK has no run-in-environment method; the managed agents API
  resumes a sandbox (its files, packages, and state) by passing
  environment=<environment_id> to interactions.create. This is confirmed against
  the live docs (the Continue the conversation section of the managed agents
  quickstart). The runner prefers the sandbox module's reuse helper so the exact
  create shape lives in one place, and falls back to a direct interactions.create
  with environment set to the candidate sandbox.
- StubFunctionalityJudge, SandboxFunctionalityJudge, FunctionalityJudge: the
  stub returns pass so the end-to-end pipe completes before sandboxes are wired;
  the sandbox judge runs the real test; the default picks the sandbox for real
  environment ids and the stub for stub ids so the loop never breaks.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional

from .config import AGENT, CLICK_BUDGET, MODEL, VIEWPORT
from .sanitize import as_str

TOOL_PATH = "/work/tool.html"
TEST_PATH = "/work/test.py"
SHOT_PATH = "/work/shot.png"
RESULT_MARKER = "ONELINE_RESULT "


class FunctionalityRunError(RuntimeError):
    """Raised when the sandbox run could not be performed or parsed."""


class FunctionalityInfraError(FunctionalityRunError):
    """Indeterminate outcome: the test infra could not actually judge the tool.

    Raised when the sandbox run could not be performed, no result marker was
    returned, or the tool never loaded and no screenshot was captured. This is a
    sentinel: the caller falls back to a default pass so a working tool is never
    disqualified by test infrastructure failure. A tool that genuinely loaded and
    failed its checks is not infra and keeps its real low score.
    """


def _slug_name(text: str, limit: int = 120) -> str:
    """A clean, human readable check name from a plan string, no long dashes."""
    name = as_str(text).strip()
    name = " ".join(name.split())
    if len(name) > limit:
        name = name[:limit].rstrip()
    return name or "criterion"


def build_checks(success_criteria: list, core_interactions: list) -> list:
    """The list of named checks the script reports, derived from the plan.

    Base checks confirm the tool runs and responds. Each success criterion
    becomes a named check evaluated by the interaction evidence the script
    gathers. core_interactions drive how many controls the script exercises.
    """
    checks = [
        {"name": "tool loads without errors", "kind": "load"},
        {"name": "primary action is present", "kind": "primary_present"},
        {"name": "primary action responds to a tap", "kind": "primary_responds"},
        {"name": "no runtime errors during use", "kind": "no_errors"},
    ]
    seen = set()
    for criterion in success_criteria or []:
        name = _slug_name(criterion)
        if name in seen:
            continue
        seen.add(name)
        checks.append({"name": name, "kind": "criterion"})
    if not (success_criteria or []):
        # Fall back to the interactions when no criteria were given.
        for interaction in core_interactions or []:
            name = _slug_name(interaction)
            if name in seen:
                continue
            seen.add(name)
            checks.append({"name": name, "kind": "criterion"})
    return checks


# The static body of the generated test. The header prepended by
# generate_playwright_test defines CHECKS, VIEWPORT, URL, SHOT, TOOL_PATH,
# TOOL_HTML_B64, and CLICK_BUDGET, so this body contains no placeholders and
# stays valid Python and JSON safe.
#
# The script is self-contained: it writes the tool HTML to TOOL_PATH itself,
# self-installs Playwright with Chromium if missing, loads file://TOOL_PATH, waits
# for load, exercises the interactions, and screenshots to SHOT. It ALWAYS prints
# a single ONELINE_RESULT line, even on internal failure, carrying navigated and
# screenshot so the judge can tell an infra failure (nothing loaded, no
# screenshot) from a tool that loaded and genuinely failed its checks.
_TEST_BODY = r'''
import base64
import pathlib
import subprocess
import sys

CHECK_NAMES = [c["name"] for c in CHECKS]


def emit(result):
    print("ONELINE_RESULT " + json.dumps(result))


def all_failed(error):
    return {
        "passed": [],
        "failed": list(CHECK_NAMES),
        "total": len(CHECK_NAMES),
        "screenshot": None,
        "navigated": False,
        "loaded": False,
        "error": error,
    }


# 1. Write the candidate tool to the known path inside this sandbox.
try:
    pathlib.Path(TOOL_PATH).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(TOOL_PATH).write_bytes(base64.b64decode(TOOL_HTML_B64))
except Exception as exc:
    emit(all_failed("write tool failed: " + repr(exc)))
    sys.exit(0)


# 2. Ensure Playwright with Chromium is available, installing only if missing.
def load_playwright():
    from playwright.sync_api import sync_playwright
    return sync_playwright


try:
    sync_playwright = load_playwright()
except Exception:
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "playwright"],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
        sync_playwright = load_playwright()
    except Exception as exc:
        emit(all_failed("playwright unavailable: " + repr(exc)))
        sys.exit(0)


JS_FIND_PRIMARY = """
() => {
  const sel = 'button, [role=button], input[type=button], input[type=submit], a[class*=btn], a[role=button]';
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const els = Array.from(document.querySelectorAll(sel)).filter(visible);
  if (!els.length) { return null; }
  els.sort((a, b) => {
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    return (rb.width * rb.height) - (ra.width * ra.height);
  });
  const el = els[0];
  el.setAttribute('data-oneline-primary', '1');
  const r = el.getBoundingClientRect();
  return {w: r.width, h: r.height, y: r.y, cy: r.y + r.height / 2,
          text: (el.innerText || el.value || '').trim()};
}
"""

JS_SIGNATURE = """
() => {
  try {
    var inputs = Array.from(document.querySelectorAll('input, textarea, select'))
      .map(function (e) { return String(e.value || ''); }).join('|');
    return JSON.stringify({
      html: document.body.innerHTML.length,
      text: (document.body.innerText || '').length,
      ls: window.localStorage.length,
      inputs: inputs
    });
  } catch (e) { return ''; }
}
"""

console_errors = []
page_errors = []
evidence = {
    "navigated": False,
    "no_load_errors": False,
    "primary_present": False,
    "primary_no_error": False,
    "primary_changed": False,
    "state_changed": False,
}
screenshot = None

# 3. Load the tool, wait for load, exercise the interactions, screenshot.
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = context.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        try:
            page.goto(URL, wait_until="load", timeout=20000)
            page.wait_for_timeout(500)
            evidence["navigated"] = True
        except Exception as exc:
            page_errors.append("goto failed: " + str(exc))
        evidence["no_load_errors"] = evidence["navigated"] and len(page_errors) == 0

        # Screenshot regardless: a captured screenshot proves the browser works,
        # which is how the judge tells a real failure from an infra failure.
        try:
            page.screenshot(path=SHOT)
            screenshot = SHOT
        except Exception:
            screenshot = None

        primary = None
        try:
            primary = page.evaluate(JS_FIND_PRIMARY)
        except Exception:
            primary = None
        evidence["primary_present"] = bool(primary)

        def signature():
            try:
                return page.evaluate(JS_SIGNATURE)
            except Exception:
                return ""

        before = signature()
        mid = before
        if primary:
            errs_before = len(page_errors)
            try:
                page.click("[data-oneline-primary]", timeout=3000)
                page.wait_for_timeout(300)
                evidence["primary_no_error"] = len(page_errors) == errs_before
            except Exception as exc:
                page_errors.append("primary click failed: " + str(exc))
                evidence["primary_no_error"] = False
            mid = signature()
        evidence["primary_changed"] = (before != mid)

        clicked = 0
        try:
            controls = page.query_selector_all(
                "button, [role=button], input[type=button], input[type=submit], a[class*=btn]"
            )
        except Exception:
            controls = []
        for control in controls:
            if clicked >= CLICK_BUDGET:
                break
            try:
                if control.is_visible():
                    control.click(timeout=1500)
                    page.wait_for_timeout(120)
                    clicked += 1
            except Exception:
                pass

        after = signature()
        evidence["state_changed"] = (before != mid) or (before != after)
        browser.close()
except Exception as exc:
    out = all_failed("playwright run failed: " + repr(exc))
    out["screenshot"] = screenshot
    out["navigated"] = evidence["navigated"]
    out["loaded"] = evidence["no_load_errors"]
    emit(out)
    sys.exit(0)

no_errors = (len(page_errors) == 0) and (len(console_errors) == 0)
interaction_ok = (
    evidence["navigated"]
    and evidence["primary_present"]
    and evidence["primary_no_error"]
    and evidence["state_changed"]
)
primary_responds = (
    evidence["primary_present"]
    and evidence["primary_no_error"]
    and (evidence["primary_changed"] or evidence["state_changed"])
)

passed = []
failed = []
for chk in CHECKS:
    kind = chk["kind"]
    if kind == "load":
        ok = evidence["no_load_errors"]
    elif kind == "primary_present":
        ok = evidence["primary_present"]
    elif kind == "primary_responds":
        ok = primary_responds
    elif kind == "no_errors":
        ok = no_errors
    else:
        ok = interaction_ok
    (passed if ok else failed).append(chk["name"])

emit({
    "passed": passed,
    "failed": failed,
    "total": len(passed) + len(failed),
    "screenshot": screenshot,
    "navigated": evidence["navigated"],
    "loaded": evidence["no_load_errors"],
    "error": None,
})
'''


def generate_playwright_test(
    success_criteria: list, core_interactions: list, html: str = ""
) -> str:
    """Build a headless Playwright script from the plan, deterministic, no model.

    The script writes the candidate HTML to /work/tool.html itself, self-installs
    Playwright with Chromium if missing, loads file:///work/tool.html, waits for
    load, finds the dominant interactive control as the primary action, taps it
    and the other controls, and screenshots to /work/shot.png. It always prints a
    single ONELINE_RESULT JSON line the judge parses, including navigated and
    screenshot so an infra failure is distinguishable from a genuine failure.
    """
    checks = build_checks(success_criteria, core_interactions)
    tool_b64 = base64.b64encode((html or "").encode("utf-8")).decode("ascii")
    header = (
        "import json\n"
        "CHECKS = " + json.dumps(checks) + "\n"
        "VIEWPORT = " + json.dumps(VIEWPORT) + "\n"
        "TOOL_PATH = " + json.dumps(TOOL_PATH) + "\n"
        "URL = " + json.dumps("file://" + TOOL_PATH) + "\n"
        "SHOT = " + json.dumps(SHOT_PATH) + "\n"
        "TOOL_HTML_B64 = " + json.dumps(tool_b64) + "\n"
        "CLICK_BUDGET = " + str(int(CLICK_BUDGET)) + "\n"
    )
    return header + _TEST_BODY


def _result_text(out: Any) -> str:
    """Pull the textual output from whatever the runner returned."""
    for attr in ("output_text", "stdout", "text", "logs", "output"):
        value = getattr(out, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    if isinstance(out, dict):
        for key in ("output_text", "stdout", "text", "logs", "output"):
            value = out.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return str(out)


def _parse_result(text: str) -> dict:
    idx = text.rfind(RESULT_MARKER)
    if idx == -1:
        # No marker means the run never reported, an indeterminate infra outcome.
        raise FunctionalityInfraError("no result marker in sandbox output")
    line = text[idx + len(RESULT_MARKER):].splitlines()[0].strip()
    try:
        return json.loads(line)
    except Exception as exc:
        raise FunctionalityInfraError("could not parse result marker: " + str(exc)) from exc


def build_run_prompt(files: dict, command: str) -> str:
    """Instruction for the agent to write the files and run the test.

    File contents are base64 encoded so the agent writes exact bytes regardless
    of quoting or markdown, then the command runs and its full standard output is
    returned. The functionality result is parsed from the ONELINE_RESULT line in
    that output, so any extra commentary the agent adds around it is harmless. The
    generated test self-installs Playwright and writes the tool to disk itself, so
    the agent only needs to write the test file, run it, and return the output.
    """
    write_lines = ["import base64, pathlib"]
    for path, content in files.items():
        encoded = base64.b64encode((content or "").encode("utf-8")).decode("ascii")
        write_lines.append(
            "pathlib.Path(%r).parent.mkdir(parents=True, exist_ok=True)" % path
        )
        write_lines.append(
            "pathlib.Path(%r).write_bytes(base64.b64decode(%r))" % (path, encoded)
        )
    writer = "\n".join(write_lines)
    return (
        "You are operating inside an existing Linux sandbox. Do exactly these "
        "steps and nothing else. Do not alter any file content.\n\n"
        "Step 1. Run this Python to write the test file with exact bytes:\n"
        "```python\n" + writer + "\n```\n\n"
        "Step 2. Run this command. The script installs Playwright and Chromium "
        "itself if they are missing, writes the tool to disk, loads it, and "
        "exercises it:\n  " + command + "\n\n"
        "Step 3. Return the complete standard output of Step 2 verbatim, "
        "including the single line that begins with ONELINE_RESULT followed by "
        "JSON. Do not summarize it, do not wrap it, do not add commentary."
    )


class ManagedAgentsRunner:
    """Reuse an existing managed sandbox to run the generated test in it.

    google-genai (2.6.0) has no run-in-environment method. The managed agents API
    resumes a sandbox, its files, packages, and state, by passing
    environment=<environment_id> to interactions.create, confirmed against the
    live docs (the Continue the conversation section of the managed agents
    quickstart). This runner builds an instruction that writes the candidate HTML
    and the Playwright test into that same sandbox and runs them, so the test runs
    in the very sandbox that built the candidate.

    It prefers the sandbox module's reuse helper (run_in_existing_environment or
    reuse_environment) so the exact create shape lives in one place; if that
    helper is not importable it falls back to a direct interactions.create with
    environment set to the candidate sandbox.
    """

    def __init__(self, client=None, agent: str = AGENT, reuse_fn=None,
                 model: "str | None" = MODEL):
        self._client = client
        self._agent = agent
        self._model = model
        self._reuse_fn = reuse_fn

    def _ensure_client(self):
        if self._client is None:
            from .gemini_client import get_client

            self._client = get_client()
        return self._client

    def _direct_reuse(self, environment_id: str, prompt: str) -> Any:
        """Fallback: call interactions.create directly, reusing the environment."""
        client = self._ensure_client()
        interactions = getattr(client, "interactions", None)
        if interactions is None or not hasattr(interactions, "create"):
            raise FunctionalityRunError("the client has no interactions.create method")
        kwargs = {"agent": self._agent, "environment": environment_id, "input": prompt}
        if self._model:
            try:
                return interactions.create(model=self._model, **kwargs)
            except TypeError:
                # This SDK build does not accept model on create; the agent
                # already carries gemini-3.5-flash.
                pass
        return interactions.create(**kwargs)

    def _resolve_reuse_fn(self):
        if self._reuse_fn is not None:
            return self._reuse_fn
        # Prefer the sandbox module's helper, which owns the exact create shape.
        helper = None
        try:
            import sandbox as sandbox_pkg  # optional, owned by the sandbox module

            helper = getattr(sandbox_pkg, "run_in_existing_environment", None) or getattr(
                sandbox_pkg, "reuse_environment", None
            )
        except Exception:
            helper = None
        if callable(helper):
            def _via_sandbox(environment_id, prompt):
                return helper(environment_id, prompt, client=self._client)

            self._reuse_fn = _via_sandbox
        else:
            self._reuse_fn = self._direct_reuse
        return self._reuse_fn

    def run(self, environment_id: str, files: dict, command: str) -> Any:
        if not environment_id:
            raise FunctionalityRunError("no environment_id to reuse")
        prompt = build_run_prompt(files, command)
        reuse = self._resolve_reuse_fn()
        return reuse(environment_id, prompt)


class StubFunctionalityJudge:
    """Returns pass so the end-to-end pipe completes before sandboxes are wired.

    Reports the plan derived check names as passed with a perfect score, no
    screenshot. Used for offline runs and stub environment ids.
    """

    def score(self, candidate: dict, plan: dict) -> dict:
        checks = build_checks(
            plan.get("success_criteria", []), plan.get("core_interactions", [])
        )
        names = [chk["name"] for chk in checks]
        return {
            "functionality_score": 1.0,
            "passed": names,
            "failed": [],
            "screenshot": None,
        }


class SandboxFunctionalityJudge:
    """The real functionality judge. Runs Playwright in the candidate sandbox."""

    def __init__(self, runner: Optional[ManagedAgentsRunner] = None):
        self.runner = runner or ManagedAgentsRunner()

    def score(self, candidate: dict, plan: dict) -> dict:
        environment_id = candidate.get("environment_id")
        if not environment_id:
            raise FunctionalityInfraError("candidate has no environment_id to reuse")
        html = candidate.get("html") or ""
        # The script embeds the tool HTML and writes it to /work/tool.html itself,
        # so only the test file is transferred into the sandbox.
        script = generate_playwright_test(
            plan.get("success_criteria", []), plan.get("core_interactions", []), html
        )
        try:
            out = self.runner.run(
                environment_id=environment_id,
                files={TEST_PATH: script},
                command="python " + TEST_PATH,
            )
        except Exception as exc:
            # Could not run in the sandbox at all: indeterminate, not a tool fault.
            raise FunctionalityInfraError("sandbox run failed: " + str(exc)) from exc

        parsed = _parse_result(_result_text(out))  # raises infra on no marker
        screenshot = parsed.get("screenshot")
        navigated = bool(parsed.get("navigated"))
        # Infra failure: the test could not load the tool and captured no
        # screenshot. Do not let this disqualify a working tool; signal
        # indeterminate so the caller falls back to a default pass.
        if not screenshot and not navigated:
            raise FunctionalityInfraError(
                "tool did not load and no screenshot was captured: "
                + as_str(parsed.get("error") or "unknown")
            )
        passed = [as_str(x) for x in parsed.get("passed", [])]
        failed = [as_str(x) for x in parsed.get("failed", [])]
        total = len(passed) + len(failed)
        score = round(len(passed) / total, 4) if total else 0.0
        return {
            "functionality_score": score,
            "passed": passed,
            "failed": failed,
            "screenshot": as_str(screenshot) if screenshot else None,
        }


def _failed_detail(plan: dict) -> dict:
    """A zeroed functionality detail: every plan check failed, no screenshot.

    Used when a real sandbox run cannot be performed. The 0.0 score is below the
    selector gate, so only that candidate is disqualified; the run continues and a
    working candidate can still win.
    """
    checks = build_checks(
        plan.get("success_criteria", []), plan.get("core_interactions", [])
    )
    names = [chk["name"] for chk in checks]
    return {
        "functionality_score": 0.0,
        "passed": [],
        "failed": names,
        "screenshot": None,
    }


class FunctionalityJudge:
    """Default functionality judge used by OnelineJudge.

    Routes real environment ids to the sandbox run, reusing the candidate's
    environment_id, and stub environment ids to the pass stub.

    The outcome of a real run is one of three things:

    - The tool loaded and the checks ran. The real score is returned and always
      honored, even when it is low. A tool that loads but fails its interactions
      is genuinely broken and keeps that low score, which can disqualify it.
    - The run was indeterminate (the sandbox could not be reached, no result was
      reported, or the tool never loaded and no screenshot was captured). This is
      a FunctionalityInfraError, a test-infrastructure failure, not a tool fault.
      The judge falls back to a default pass so a working tool is never killed by
      flaky infra. This is the critical guard.
    - Some other unexpected error. The on_error policy decides: "stub" falls back
      to pass (default), "zero" disqualifies just that candidate, "raise"
      surfaces it.

    strict is kept for compatibility: strict True maps to "raise", False to
    "stub".
    """

    def __init__(self, runner: Optional[ManagedAgentsRunner] = None,
                 on_error: str = "stub", strict: "bool | None" = None):
        if strict is not None:
            on_error = "raise" if strict else "stub"
        if on_error not in ("stub", "zero", "raise"):
            raise ValueError("on_error must be one of stub, zero, raise")
        self.on_error = on_error
        self._stub = StubFunctionalityJudge()
        self._sandbox = SandboxFunctionalityJudge(runner=runner)

    def score(self, candidate: dict, plan: dict) -> dict:
        environment_id = str(candidate.get("environment_id") or "")
        if not environment_id or environment_id.startswith("stub"):
            return self._stub.score(candidate, plan)
        try:
            return self._sandbox.score(candidate, plan)
        except FunctionalityInfraError:
            # Indeterminate: the test infra could not judge the tool. Fall back to
            # a default pass so a working tool is never disqualified by infra.
            return self._stub.score(candidate, plan)
        except Exception:
            if self.on_error == "raise":
                raise
            if self.on_error == "zero":
                return _failed_detail(plan)
            return self._stub.score(candidate, plan)
