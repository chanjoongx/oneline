"""Thin wrapper around the Gemini Managed Agents interactions API.

Confirmed working shape (tested, and matches the official docs at
ai.google.dev/gemini-api/docs/managed-agents-quickstart and
ai.google.dev/gemini-api/docs/agent-environment):

    client = genai.Client(api_key=...)

    # Build: provision a fresh sandbox.
    interaction = client.interactions.create(
        agent="antigravity-preview-05-2026",
        input=prompt,
        environment="remote",            # spawns an isolated Linux sandbox
    )
    interaction.output_text     # the model's text output
    interaction.id              # interaction id
    interaction.environment_id  # the sandbox id, reused by the functionality judge
    interaction.steps           # list of agent actions taken

    # Reuse: run a command in the SAME sandbox that built the candidate.
    follow_up = client.interactions.create(
        agent="antigravity-preview-05-2026",
        environment=interaction.environment_id,   # the existing sandbox, by id
        previous_interaction_id=interaction.id,   # optional conversation continuity
        input="Run this command and report stdout, stderr, exit code: ...",
    )

Per the docs, commands and file operations happen through the natural-language
`input` (there is no dedicated command, exec, or files parameter). Reusing a
sandbox needs only its environment_id string; previous_interaction_id is an
optional continuity hint.

Two things this wrapper guarantees:
  1. It raises the output token cap (config.MAX_OUTPUT_TOKENS) so larger
     self-contained tools are not truncated mid-script.
  2. It drops optional kwargs the SDK does not accept, so the call works across
     SDK builds, while always sending the core fields.

The google-genai SDK is imported lazily so this package stays importable for the
deterministic paths and offline tests without the SDK or an API key present.
"""
from __future__ import annotations

import base64
import re

from .config import (
    AGENT,
    DEFAULT_SCREENSHOT_PATH,
    DEFAULT_TOOL_PATH,
    IMPLEMENTER_MODEL,
    MAX_OUTPUT_TOKENS,
    REMOTE_ENV,
    SANDBOX_WORKDIR,
    gemini_api_key,
)

DEFAULT_TEST_PATH = SANDBOX_WORKDIR + "/test.py"

# Template that turns a shell command into a run-and-report instruction with a
# parseable output contract, so the functionality judge can read stdout, stderr,
# and exit code deterministically from output_text.
RUN_AND_REPORT = (
    "Run the following command inside this sandbox shell, then report its result "
    "and nothing else. Do not explain. Use exactly this format:\n"
    "STDOUT:\n<the full standard output>\n"
    "STDERR:\n<the full standard error>\n"
    "EXIT_CODE: <the integer exit code>\n\n"
    "Command:\n{command}\n"
)

# Write a file into the sandbox by base64 so the exact bytes land, with no
# escaping or reformatting of the HTML. The agent decodes and writes verbatim.
WRITE_FILE = (
    "Write a file to the path {path} in this sandbox. Take the base64 text between "
    "BEGIN_BASE64 and END_BASE64, decode it, and write the exact decoded bytes to "
    "{path} with no changes. After writing, report only this line:\n"
    "WROTE: {path} (<byte count> bytes)\n\n"
    "BEGIN_BASE64\n{b64}\nEND_BASE64\n"
)

# Install Playwright and a Chromium build inside the sandbox. The --with-deps
# path needs root (the managed sandbox usually has it); the fallback runs without
# system deps if it does not.
INSTALL_PLAYWRIGHT = (
    "pip install --quiet playwright && "
    "(python -m playwright install --with-deps chromium || "
    "python -m playwright install chromium)"
)

# Read a file out of the sandbox. EXISTS and SIZE are always reported so the
# caller can confirm a screenshot was actually captured; the base64 contents are
# included only when requested, to avoid large outputs.
READ_FILE = (
    "Report whether the file {path} exists in this sandbox, and nothing else. "
    "Use exactly this format:\n"
    "FILE: {path}\n"
    "EXISTS: <true or false>\n"
    "SIZE: <byte count, or 0>\n"
)
READ_FILE_WITH_CONTENTS = READ_FILE + (
    "BASE64:\n<the base64 encoding of the file bytes, or empty if it does not exist>\n"
)


def get_client():
    """Create a google-genai client using GEMINI_API_KEY from the environment."""
    from google import genai  # lazy import, keeps the package importable offline

    key = gemini_api_key()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set in the environment. Set it before live runs."
        )
    return genai.Client(api_key=key)


def _generation_config(max_output_tokens):
    """Build a GenerateContentConfig that raises the output cap, or None offline."""
    if not max_output_tokens:
        return None
    try:
        from google.genai import types
    except Exception:
        return None
    try:
        return types.GenerateContentConfig(max_output_tokens=max_output_tokens)
    except Exception:
        return None


_UNSUPPORTED_KW = ("unexpected keyword", "got an unexpected", "takes no", "no parameter")


def _is_unsupported_kwarg(exc) -> bool:
    """True when a TypeError is about a kwarg the SDK does not accept."""
    msg = str(exc).lower()
    return any(s in msg for s in _UNSUPPORTED_KW)


def _create(client, base_kwargs, *, model=None, previous_interaction_id=None,
            max_output_tokens=None):
    """interactions.create with optional kwargs, dropping any the SDK rejects.

    Raises the output token cap so larger self-contained tools are not truncated.
    Tries the richest signature first and removes only kwargs the SDK reports as
    unsupported; any other error propagates. The core fields (agent, input,
    environment) are always sent.
    """
    cfg = _generation_config(max_output_tokens)
    caps = []
    if cfg is not None:
        caps.append({"config": cfg})
    if max_output_tokens:
        caps.append({"max_output_tokens": max_output_tokens})
    caps.append({})

    models = ([{"model": model}] if model else []) + [{}]
    prevs = ([{"previous_interaction_id": previous_interaction_id}]
             if previous_interaction_id else []) + [{}]

    last_exc = None
    for cap in caps:
        for mdl in models:
            for prev in prevs:
                kwargs = {**base_kwargs, **cap, **mdl, **prev}
                try:
                    return client.interactions.create(**kwargs)
                except TypeError as exc:
                    if not _is_unsupported_kwarg(exc):
                        raise
                    last_exc = exc
    if last_exc:
        raise last_exc
    return client.interactions.create(**base_kwargs)


def create_interaction(prompt: str, client=None, *, environment: str = REMOTE_ENV,
                       previous_interaction_id: "str | None" = None,
                       model: "str | None" = IMPLEMENTER_MODEL, agent: str = AGENT,
                       max_output_tokens: "int | None" = MAX_OUTPUT_TOKENS):
    """Create one managed-agents interaction.

    environment="remote" spawns a fresh isolated sandbox. Pass an existing
    environment_id instead to reuse a sandbox. model defaults to gemini-3.5-flash
    and is passed only when the SDK accepts it; the agent otherwise carries it.
    max_output_tokens raises the output cap so the full HTML is returned.
    previous_interaction_id is an optional continuity hint when reusing a sandbox.
    """
    client = client or get_client()
    base = {"agent": agent, "input": prompt, "environment": environment}
    return _create(client, base, model=model,
                   previous_interaction_id=previous_interaction_id,
                   max_output_tokens=max_output_tokens)


def reuse_environment(environment_id: str, prompt: str, client=None, *,
                      previous_interaction_id: "str | None" = None,
                      model: "str | None" = IMPLEMENTER_MODEL,
                      max_output_tokens: "int | None" = MAX_OUTPUT_TOKENS):
    """Run another interaction inside an existing sandbox with a raw input prompt.

    Low-level passthrough for multi-step instructions (for example: write
    tool.html, write a test, run it, report a result). The functionality judge
    passes the candidate's environment_id to operate in the same sandbox the tool
    was built in. The judge owns the test logic; this provides the reuse call.
    """
    return create_interaction(
        prompt, client, environment=environment_id,
        previous_interaction_id=previous_interaction_id, model=model,
        max_output_tokens=max_output_tokens,
    )


def run_in_existing_environment(environment_id: str, command: str, client=None, *,
                                previous_interaction_id: "str | None" = None,
                                model: "str | None" = IMPLEMENTER_MODEL,
                                max_output_tokens: "int | None" = MAX_OUTPUT_TOKENS,
                                report: bool = True):
    """Run a shell command in an existing sandbox and return the interaction.

    The clean helper for the functionality judge: pass the candidate's
    environment_id and a command to run in the very sandbox that built the
    candidate. With report=True (default) the command is wrapped in a
    run-and-report instruction (RUN_AND_REPORT) so output_text carries STDOUT,
    STDERR, and EXIT_CODE in a parseable form. With report=False the command is
    sent as the raw input. Read the result from the returned interaction's
    output_text.
    """
    instruction = RUN_AND_REPORT.format(command=command) if report else command
    return reuse_environment(
        environment_id, instruction, client,
        previous_interaction_id=previous_interaction_id, model=model,
        max_output_tokens=max_output_tokens,
    )


def write_file_to_environment(environment_id: str, path: str, content, client=None,
                              *, previous_interaction_id: "str | None" = None,
                              max_output_tokens: "int | None" = MAX_OUTPUT_TOKENS):
    """Write a file into an existing sandbox as exact bytes, via base64.

    The functionality judge uses this to place the candidate HTML and its test
    into the sandbox before running. content may be str (encoded utf-8) or bytes.
    Base64 guarantees the HTML lands byte for byte with no escaping or edits.
    Returns the interaction; output_text reports "WROTE: <path> (<n> bytes)".
    """
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    b64 = base64.b64encode(data).decode("ascii")
    instruction = WRITE_FILE.format(path=path, b64=b64)
    return reuse_environment(
        environment_id, instruction, client,
        previous_interaction_id=previous_interaction_id,
        max_output_tokens=max_output_tokens,
    )


def ensure_playwright_in_environment(environment_id: str, client=None, *,
                                     previous_interaction_id: "str | None" = None,
                                     max_output_tokens: "int | None" = MAX_OUTPUT_TOKENS):
    """Install Playwright and Chromium in an existing sandbox. Returns the run."""
    return run_in_existing_environment(
        environment_id, INSTALL_PLAYWRIGHT, client,
        previous_interaction_id=previous_interaction_id,
        max_output_tokens=max_output_tokens,
    )


def read_file_from_environment(environment_id: str, path: str = DEFAULT_SCREENSHOT_PATH,
                               client=None, *, include_contents: bool = False,
                               previous_interaction_id: "str | None" = None,
                               max_output_tokens: "int | None" = MAX_OUTPUT_TOKENS):
    """Read a file (default the screenshot) out of an existing sandbox.

    Use this to confirm a screenshot was actually captured. EXISTS and SIZE are
    always reported, so a null or zero result tells the judge the capture step
    failed rather than silently passing screenshot=null. Set include_contents to
    also return the file as base64 (keep images small, base64 inflates output).
    Returns the interaction; output_text carries the FILE / EXISTS / SIZE block.
    """
    template = READ_FILE_WITH_CONTENTS if include_contents else READ_FILE
    instruction = template.format(path=path)
    return reuse_environment(
        environment_id, instruction, client,
        previous_interaction_id=previous_interaction_id,
        max_output_tokens=max_output_tokens,
    )


# A minimal Playwright smoke test: load the tool from a file URL at a 390px
# viewport, screenshot it, and print a JSON result. Placeholders are replaced (not
# str.format) so the braces in the script stay intact. The functionality judge can
# pass its own richer test to run_functionality_test instead.
_DEFAULT_PLAYWRIGHT_TEST = (
    "import json\n"
    "from playwright.sync_api import sync_playwright\n"
    "TOOL = 'file://__TOOL_PATH__'\n"
    "SHOT = '__SHOT_PATH__'\n"
    "result = {'loaded': False, 'title': None, 'errors': []}\n"
    "with sync_playwright() as p:\n"
    "    browser = p.chromium.launch()\n"
    "    page = browser.new_page(viewport={'width': 390, 'height': 844})\n"
    "    page.on('pageerror', lambda e: result['errors'].append(str(e)))\n"
    "    page.goto(TOOL, wait_until='load')\n"
    "    result['loaded'] = True\n"
    "    result['title'] = page.title()\n"
    "    page.screenshot(path=SHOT, full_page=True)\n"
    "    browser.close()\n"
    "print('RESULT_JSON ' + json.dumps(result))\n"
)


def default_playwright_test(tool_path: str = DEFAULT_TOOL_PATH,
                            screenshot_path: str = DEFAULT_SCREENSHOT_PATH) -> str:
    """Return the default smoke test that loads the tool and screenshots it."""
    return (
        _DEFAULT_PLAYWRIGHT_TEST
        .replace("__TOOL_PATH__", tool_path)
        .replace("__SHOT_PATH__", screenshot_path)
    )


_RUN_RE = re.compile(
    r"STDOUT:\s*\n(.*?)\nSTDERR:\s*\n(.*?)\nEXIT_CODE:\s*(-?\d+)", re.DOTALL
)
_FILE_PATH_RE = re.compile(r"FILE:\s*(\S+)")
_EXISTS_RE = re.compile(r"EXISTS:\s*(true|false)", re.IGNORECASE)
_SIZE_RE = re.compile(r"SIZE:\s*(\d+)")
_B64_RE = re.compile(r"BASE64:\s*\n([A-Za-z0-9+/=\s]*)")


def parse_run_report(output_text: str) -> dict:
    """Parse a RUN_AND_REPORT output into stdout, stderr, exit_code."""
    text = output_text or ""
    match = _RUN_RE.search(text)
    if match:
        return {
            "stdout": match.group(1).strip(),
            "stderr": match.group(2).strip(),
            "exit_code": int(match.group(3)),
        }
    return {"stdout": text.strip(), "stderr": "", "exit_code": None}


def parse_file_report(output_text: str) -> dict:
    """Parse a READ_FILE output into path, exists, size, and optional base64."""
    text = output_text or ""
    path = _FILE_PATH_RE.search(text)
    exists = _EXISTS_RE.search(text)
    size = _SIZE_RE.search(text)
    b64 = _B64_RE.search(text)
    return {
        "path": path.group(1) if path else None,
        "exists": bool(exists) and exists.group(1).lower() == "true",
        "size": int(size.group(1)) if size else 0,
        "base64": ("".join(b64.group(1).split()) or None) if b64 else None,
    }


def run_functionality_test(environment_id: str, html: str, test_script: "str | None" = None,
                           client=None, *, tool_path: str = DEFAULT_TOOL_PATH,
                           test_path: str = DEFAULT_TEST_PATH,
                           screenshot_path: str = DEFAULT_SCREENSHOT_PATH,
                           ensure_browser: bool = True,
                           previous_interaction_id: "str | None" = None,
                           max_output_tokens: "int | None" = MAX_OUTPUT_TOKENS) -> dict:
    """Run a Playwright functionality test in the candidate's own sandbox.

    Writes the tool HTML (exact bytes) to tool_path and the test to test_path,
    optionally installs Playwright and Chromium, runs the test, then reads the
    screenshot back to confirm it was captured. With no test_script, a default
    smoke test loads file://<tool_path> at 390px and screenshots it, which
    verifies the file path and the load actually work in the reused environment.

    Returns the parsed run result and a screenshot path that is None when the
    capture did not happen (so the judge never silently records screenshot=null):

        {"environment_id", "exit_code", "stdout", "stderr",
         "screenshot_path", "screenshot_exists", "screenshot_size", "raw"}
    """
    client = client or get_client()
    if test_script is None:
        test_script = default_playwright_test(tool_path, screenshot_path)

    raw = {}
    raw["write_tool"] = write_file_to_environment(
        environment_id, tool_path, html, client, max_output_tokens=max_output_tokens
    ).output_text
    raw["write_test"] = write_file_to_environment(
        environment_id, test_path, test_script, client, max_output_tokens=max_output_tokens
    ).output_text
    if ensure_browser:
        raw["ensure_browser"] = ensure_playwright_in_environment(
            environment_id, client, max_output_tokens=max_output_tokens
        ).output_text
    run = run_in_existing_environment(
        environment_id, "python " + test_path, client,
        previous_interaction_id=previous_interaction_id,
        max_output_tokens=max_output_tokens,
    )
    raw["run"] = run.output_text
    shot = read_file_from_environment(
        environment_id, screenshot_path, client, max_output_tokens=max_output_tokens
    )
    raw["read_screenshot"] = shot.output_text

    run_report = parse_run_report(run.output_text)
    shot_report = parse_file_report(shot.output_text)
    captured = shot_report["exists"] and shot_report["size"] > 0
    return {
        "environment_id": environment_id,
        "exit_code": run_report["exit_code"],
        "stdout": run_report["stdout"],
        "stderr": run_report["stderr"],
        "screenshot_path": screenshot_path if captured else None,
        "screenshot_exists": shot_report["exists"],
        "screenshot_size": shot_report["size"],
        "raw": raw,
    }


def step_count(interaction) -> int:
    """Number of agent steps, tolerant of list, int, or missing."""
    steps = getattr(interaction, "steps", None)
    if steps is None:
        return 0
    if isinstance(steps, int):
        return steps
    try:
        return len(steps)
    except TypeError:
        return 0
