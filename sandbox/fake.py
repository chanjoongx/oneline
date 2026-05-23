"""An offline stand-in for the Gemini Managed Agents client.

It mimics client.interactions.create(agent, input, environment, model, ...) and
returns an object with output_text, id, environment_id, and steps, exactly like
the real interaction. A fresh sandbox builds a valid, design-system-conforming,
self-contained tool; a reused sandbox simulates running a command, writing a
file, or reading a file (including a screenshot), so the whole sandbox path and
the functionality judge plumbing run end to end without an API key or credits.

It can also simulate output truncation (truncate_first) so the completeness
guard and extraction can be tested. This is not used on the live path. The real
path uses sandbox.client.get_client.
"""
from __future__ import annotations

import base64
import re
import threading
import uuid

from .config import ACCENT_BLUE, DEFAULT_SCREENSHOT_PATH
from .prompts import load_base_css

_ACCENT_IN_PROMPT = re.compile(r"accent chosen for this tool is\s*(#[0-9A-Fa-f]{6})", re.IGNORECASE)
_COMMAND_IN_PROMPT = re.compile(r"Command:\s*\n(.+)", re.IGNORECASE | re.DOTALL)
_WRITE_PATH = re.compile(r"Write a file to the path\s+(\S+)\s+in this sandbox", re.IGNORECASE)
_WRITE_BODY = re.compile(r"BEGIN_BASE64\n(.*?)\nEND_BASE64", re.DOTALL)
_READ_PATH = re.compile(r"Report whether the file\s+(\S+)\s+exists", re.IGNORECASE)
_RUN_PY = re.compile(r"python\s+(/\S+\.py)")
_SHOT_IN_TEST = re.compile(
    r"screenshot\(\s*path\s*=\s*['\"]([^'\"]+)['\"]|\bSHOT\b\s*=\s*['\"]([^'\"]+)['\"]"
)

# A tiny but valid PNG header so a read-back reports a non-zero size.
_FAKE_PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"oneline-fake-screenshot"


def _screenshot_path_from_test(src: str) -> "str | None":
    match = _SHOT_IN_TEST.search(src or "")
    if not match:
        return None
    return match.group(1) or match.group(2)


def _accent_from_prompt(prompt: str) -> str:
    match = _ACCENT_IN_PROMPT.search(prompt or "")
    return match.group(1) if match else ACCENT_BLUE


def _fake_tool_html(accent: str) -> str:
    """A small valid counter tool: dark base, one accent, one hero, one action."""
    css = load_base_css()
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        "<title>Oneline tool</title>\n<style>\n"
        + css
        + "\n:root { --accent: " + accent + "; }\n"
        ".count-wrap{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:var(--space-2)}\n"
        "</style>\n</head>\n<body>\n"
        '<main class="ol-app">\n'
        '  <h1 class="ol-title">Count</h1>\n'
        '  <div class="count-wrap">\n'
        '    <div class="ol-label">Tally so far</div>\n'
        '    <div class="ol-hero ol-hero--live" id="value">0</div>\n'
        "  </div>\n"
        '  <div class="ol-dock">\n'
        '    <button class="ol-btn ol-btn-primary" id="add">Add one</button>\n'
        "  </div>\n"
        "</main>\n<script>\n"
        "var v=document.getElementById('value');\n"
        "var n=parseInt(localStorage.getItem('oneline_count')||'0',10);\n"
        "v.textContent=n;\n"
        "document.getElementById('add').addEventListener('click',function(){\n"
        "  n=n+1; v.textContent=n; localStorage.setItem('oneline_count',String(n));\n"
        "});\n"
        "</script>\n</body>\n</html>\n"
    )


def _truncated_build_output(accent: str) -> str:
    """A build whose HTML is cut off mid-script with no closing fence, like a
    response that hit the output token cap."""
    html = _fake_tool_html(accent)
    cut = html.split("v.textContent=n;")[0] + "v.textContent=n;\n// output cut off here"
    return "```html\n" + html[: len(cut)]


class _FakeInteraction:
    def __init__(self, output_text: str, environment: str):
        self.output_text = output_text
        self.id = "int_" + uuid.uuid4().hex[:10]
        # A reused sandbox keeps its id; a remote request gets a fresh one.
        self.environment_id = (
            environment if environment != "remote" else "env_" + uuid.uuid4().hex[:10]
        )
        self.steps = ["plan", "write", "verify"]


class _FakeInteractions:
    def __init__(self, truncate_first: int = 0):
        self._truncate_left = truncate_first
        self._files = {}
        self._lock = threading.Lock()

    def create(self, agent, input, environment="remote",  # noqa: A002
               model=None, previous_interaction_id=None, **_):
        if environment != "remote":
            return self._reuse(input, environment)
        return self._build(input, environment)

    def _build(self, prompt, environment):
        accent = _accent_from_prompt(prompt)
        with self._lock:
            truncate = self._truncate_left > 0
            if truncate:
                self._truncate_left -= 1
        if truncate:
            return _FakeInteraction(_truncated_build_output(accent), environment)
        html = _fake_tool_html(accent)
        # A stray em dash in the rationale proves sanitization works downstream.
        output = (
            "```html\n" + html + "\n```\n"
            "Rationale: accent " + accent + " chosen to fit the tool - hero count "
            "centered with one full-width action in the thumb zone.\n"
        )
        return _FakeInteraction(output, environment)

    def _reuse(self, prompt, environment):
        write_path = _WRITE_PATH.search(prompt)
        read_path = _READ_PATH.search(prompt)
        if write_path:
            path = write_path.group(1)
            body = _WRITE_BODY.search(prompt)
            try:
                data = base64.b64decode(body.group(1)) if body else b""
            except Exception:
                data = b""
            with self._lock:
                self._files[(environment, path)] = data
            return _FakeInteraction(f"WROTE: {path} ({len(data)} bytes)\n", environment)
        if read_path:
            path = read_path.group(1)
            with self._lock:
                data = self._files.get((environment, path))
            exists = data is not None
            size = len(data) if exists else 0
            output = f"FILE: {path}\nEXISTS: {str(exists).lower()}\nSIZE: {size}\n"
            if "BASE64:" in prompt:
                b64 = base64.b64encode(data).decode("ascii") if exists else ""
                output += "BASE64:\n" + b64 + "\n"
            return _FakeInteraction(output, environment)
        # Otherwise a run-and-report command.
        cmd = _COMMAND_IN_PROMPT.search(prompt)
        command = cmd.group(1).strip() if cmd else prompt.strip()
        run_py = _RUN_PY.search(command)
        if run_py:
            return self._run_test(environment, run_py.group(1))
        output = (
            "STDOUT:\n"
            f"(simulated run in {environment}) {command}\n"
            "STDERR:\n\n"
            "EXIT_CODE: 0\n"
        )
        return _FakeInteraction(output, environment)

    def _run_test(self, environment, test_path):
        """Simulate running a Playwright test: read the test, load the tool, and
        write the screenshot it asks for, then report a passing run."""
        with self._lock:
            test_bytes = self._files.get((environment, test_path), b"")
            tool_present = (environment, "/work/tool.html") in self._files
        src = test_bytes.decode("utf-8", "ignore")
        shot = _screenshot_path_from_test(src) or DEFAULT_SCREENSHOT_PATH
        with self._lock:
            self._files[(environment, shot)] = _FAKE_PNG
        loaded = "true" if tool_present else "false"
        output = (
            "STDOUT:\n"
            'RESULT_JSON {"loaded": ' + loaded + ', "title": "Oneline tool", "errors": []}\n'
            "STDERR:\n\n"
            "EXIT_CODE: 0\n"
        )
        return _FakeInteraction(output, environment)


class FakeManagedClient:
    """Drop-in replacement for a google-genai client on the sandbox path.

    truncate_first simulates the first N builds hitting the output token cap, so
    the completeness guard and rebuild path can be tested.
    """

    def __init__(self, truncate_first: int = 0):
        self.interactions = _FakeInteractions(truncate_first=truncate_first)
