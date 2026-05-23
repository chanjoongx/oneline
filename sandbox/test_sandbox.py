"""Offline tests for the sandbox module. No API key, no network.

Run: python -m sandbox.test_sandbox
Covers: prompt assembly, HTML and rationale extraction, em dash sanitization,
accent resolution, candidate shape against the shared schema, the single-build
path, and the parallel three-build path. Uses the fake managed client.
"""
from __future__ import annotations

import json
import sys

from .accents import normalize_accent, recommend_accent
from .client import (
    create_interaction,
    default_playwright_test,
    parse_file_report,
    parse_run_report,
    read_file_from_environment,
    reuse_environment,
    run_functionality_test,
    run_in_existing_environment,
    write_file_to_environment,
)
from .config import CANDIDATE_SCHEMA_PATH, DEFAULT_SCREENSHOT_PATH, DEFAULT_TOOL_PATH
from .extract import (
    assert_no_em_dash,
    extract_accent,
    extract_html,
    extract_rationale,
    has_long_dash,
    html_problems,
    is_html_complete,
    strip_long_dashes,
)
from .fake import FakeManagedClient
from .implementer import IncompleteHTMLError, ManagedAgentsImplementer
from .prompts import (
    core_interactions_from_brief,
    render_implementer_prompt,
    tool_category_from_brief,
)

_STRATEGIES = [
    {"id": "A", "framework": "vanilla_html", "ux_emphasis": "speed_minimal"},
    {"id": "B", "framework": "tailwind_cdn", "ux_emphasis": "polish"},
    {"id": "C", "framework": "tailwind_cdn", "ux_emphasis": "minimal_whitespace"},
]

_BRIEF = "\n".join(
    [
        "User need: A flashcard set for ten Korean words",
        "Tool category: flashcards",
        "Core interactions: ['Flip a card', 'Advance to the next card']",
        "Data model: Cards array in localStorage, current index in memory.",
        "Success criteria: ['Tapping a card flips it', 'Advancing shows the next card']",
    ]
)

_LESSONS = [
    {
        "id": "lesson_001",
        "lesson_text": "Primary action must sit in the bottom third for thumb reach.",
        "good_pattern": "bottom-center sticky full-width action",
        "relevance_score": 0.9,
    }
]


def _load_schema():
    return json.loads(CANDIDATE_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_candidate(candidate: dict) -> None:
    import jsonschema

    jsonschema.validate(candidate, _load_schema())


def _check(name: str, condition: bool) -> bool:
    print(f"  {'ok  ' if condition else 'FAIL'} {name}")
    return condition


def test_extract() -> bool:
    text = (
        "preamble\n```html\n<!doctype html><html><body>"
        "<style>:root{--accent:#A371F7;}</style>x</body></html>\n```\n"
        "Rationale: violet accent for learning - card centered.\n"
    )
    html = extract_html(text)
    rationale = extract_rationale(text)
    accent = extract_accent(html)
    ok = True
    ok &= _check("extract_html grabs the fenced block", html.startswith("<!doctype html>"))
    ok &= _check("extract_rationale grabs the rationale line", rationale.startswith("Rationale:"))
    ok &= _check("extract_accent reads the active accent", accent == "#A371F7")
    return ok


def test_accent_logic() -> bool:
    ok = True
    ok &= _check("flashcards recommend violet", recommend_accent("flashcards") == "#A371F7")
    ok &= _check("tracker recommends green", recommend_accent("tracker") == "#3FB950")
    ok &= _check("countdown cue wins amber", recommend_accent("timer", "a countdown to my trip") == "#E3A008")
    ok &= _check("interval cue wins red", recommend_accent("timer", "hiit interval timer") == "#F85149")
    ok &= _check("off-system hex rejected", normalize_accent("#123456") is None)
    ok &= _check("approved hex normalized", normalize_accent("#a371f7") == "#A371F7")
    return ok


def test_em_dash() -> bool:
    # Build the dirty inputs from code points so this test file has no long-dash
    # byte of its own. chr(0x2014) is the em dash, chr(0x2013) the en dash.
    dirty = "a long dash " + chr(0x2014) + " here and an en dash " + chr(0x2013) + " there"
    clean, count = strip_long_dashes(dirty)
    ok = True
    ok &= _check("strip counts the dashes", count == 2)
    ok &= _check("clean has no long dash", not has_long_dash(clean))
    raised = False
    try:
        assert_no_em_dash("nope " + chr(0x2014) + " nope")
    except ValueError:
        raised = True
    ok &= _check("assert_no_em_dash raises on em dash", raised)
    return ok


def test_prompt_assembly() -> bool:
    accent = recommend_accent(tool_category_from_brief(_BRIEF), _BRIEF)
    prompt = render_implementer_prompt(_STRATEGIES[2], _BRIEF, _LESSONS, accent)
    ok = True
    ok &= _check("prompt names the candidate", "Implementer C" in prompt)
    ok &= _check("prompt inlines base.css tokens", "--accent-ink" in prompt)
    ok &= _check("prompt carries the chosen accent", accent in prompt)
    ok &= _check("prompt states the emphasis", "minimal_whitespace" in prompt)
    ok &= _check("prompt forbids em dashes", "No em dashes" in prompt or "em dashes" in prompt)
    ok &= _check("prompt forbids remote fetch", "No fetch" in prompt)
    ok &= _check("prompt has no em dash itself", not has_long_dash(prompt))
    return ok


def test_build_one() -> bool:
    impl = ManagedAgentsImplementer(client=FakeManagedClient())
    cand = impl.build_candidate(_STRATEGIES[0], _BRIEF, _LESSONS)
    ok = True
    ok &= _check("candidate_id is A", cand["candidate_id"] == "A")
    ok &= _check("has environment_id", bool(cand["environment_id"]))
    ok &= _check("html present", "<!doctype html>" in cand["html"].lower())
    ok &= _check("no long dash in html", not has_long_dash(cand["html"]))
    ok &= _check("no long dash in rationale", not has_long_dash(cand["rationale"]))
    ok &= _check("accent is approved", cand["accent"] in {
        "#5B8DEF", "#3FB950", "#E3A008", "#A371F7", "#F85149", "#2DD4BF"
    })
    try:
        _validate_candidate(cand)
        ok &= _check("candidate passes shared schema", True)
    except Exception as exc:  # pragma: no cover - error path
        ok &= _check(f"candidate passes shared schema ({exc})", False)
    return ok


def test_build_parallel() -> bool:
    impl = ManagedAgentsImplementer(client=FakeManagedClient())
    cands = impl.build_candidates(_STRATEGIES, _BRIEF, _LESSONS)
    ids = [c["candidate_id"] for c in cands]
    env_ids = [c["environment_id"] for c in cands]
    ok = True
    ok &= _check("three candidates returned", len(cands) == 3)
    ok &= _check("order preserved A B C", ids == ["A", "B", "C"])
    ok &= _check("every candidate has an environment_id", all(env_ids))
    ok &= _check("environment_ids are distinct sandboxes", len(set(env_ids)) == 3)
    for c in cands:
        try:
            _validate_candidate(c)
        except Exception:  # pragma: no cover - error path
            ok = False
    ok &= _check("all three pass the shared schema", ok)
    return ok


def test_reuse_sandbox() -> bool:
    # Build a candidate to get a real sandbox id, then run a command in it.
    client = FakeManagedClient()
    impl = ManagedAgentsImplementer(client=client)
    cand = impl.build_candidate(_STRATEGIES[0], _BRIEF, _LESSONS)
    env_id = cand["environment_id"]

    run = run_in_existing_environment(
        env_id, "ls -la /work", client, previous_interaction_id="int_x"
    )
    reuse = reuse_environment(env_id, "Report the contents of /work", client)
    ok = True
    ok &= _check("run helper targets the same sandbox", run.environment_id == env_id)
    ok &= _check("run helper reports an exit code", "EXIT_CODE:" in run.output_text)
    ok &= _check("run helper echoes the command", "ls -la /work" in run.output_text)
    ok &= _check("reuse helper targets the same sandbox", reuse.environment_id == env_id)
    return ok


def test_sdk_fallback() -> bool:
    # An SDK that rejects model and previous_interaction_id must still work via
    # the progressive-drop fallback in client._create.
    class StrictInteractions:
        def __init__(self):
            self.seen = None

        def create(self, agent, input, environment="remote"):  # noqa: A002
            self.seen = (agent, environment)

            class R:
                output_text = "ok"
                id = "int_strict"
                environment_id = environment
                steps = []

            return R()

    class StrictClient:
        def __init__(self):
            self.interactions = StrictInteractions()

    client = StrictClient()
    res = create_interaction(
        "hello", client, environment="env_strict",
        previous_interaction_id="int_prev", model="gemini-3.5-flash",
    )
    ok = True
    ok &= _check("fallback drops unsupported kwargs and succeeds", res.output_text == "ok")
    ok &= _check("fallback keeps the core fields", client.interactions.seen == (
        "antigravity-preview-05-2026", "env_strict"
    ))
    return ok


def test_completeness_checks() -> bool:
    complete = "<!doctype html><html><head><style>a{}</style></head><body>"\
        "<script>var x=1;</script></body></html>"
    truncated = "<!doctype html><html><head><style>a{}</style></head><body>"\
        "<script>var x=1;"  # cut off mid-script
    ok = True
    ok &= _check("complete html has no problems", is_html_complete(complete))
    probs = html_problems(truncated)
    ok &= _check("truncated html is flagged", not is_html_complete(truncated))
    ok &= _check("flags missing closing html", any("</html>" in p for p in probs))
    ok &= _check("flags unbalanced script", any("script" in p for p in probs))
    return ok


def test_extract_truncated() -> bool:
    # Open fence, no closing fence, cut off mid-script. Must return the partial
    # HTML, not the code-fence wrapper text, so the guard can flag it.
    text = "Here is the tool:\n```html\n<!doctype html><html><body><script>var x=1;"
    html = extract_html(text)
    ok = True
    ok &= _check("does not return the fence marker", not html.startswith("```"))
    ok &= _check("captures the partial html", html.startswith("<!doctype html>"))
    ok &= _check("partial html is flagged incomplete", not is_html_complete(html))
    return ok


def test_guard_raises() -> bool:
    impl = ManagedAgentsImplementer(
        client=FakeManagedClient(truncate_first=99), max_build_attempts=2
    )
    raised = False
    try:
        impl.build_candidate(_STRATEGIES[0], _BRIEF, _LESSONS)
    except IncompleteHTMLError as exc:
        raised = exc.candidate_id == "A" and bool(exc.problems)
    return _check("guard raises IncompleteHTMLError on persistent truncation", raised)


def test_guard_retry_recovers() -> bool:
    # First build truncates, the rebuild completes within max_build_attempts.
    impl = ManagedAgentsImplementer(
        client=FakeManagedClient(truncate_first=1), max_build_attempts=2
    )
    cand = impl.build_candidate(_STRATEGIES[0], _BRIEF, _LESSONS)
    ok = True
    ok &= _check("retry recovered a complete candidate", is_html_complete(cand["html"]))
    ok &= _check("recovered candidate has environment_id", bool(cand["environment_id"]))
    return ok


def test_file_io() -> bool:
    client = FakeManagedClient()
    impl = ManagedAgentsImplementer(client=client)
    cand = impl.build_candidate(_STRATEGIES[0], _BRIEF, _LESSONS)
    env_id = cand["environment_id"]

    wrote = write_file_to_environment(env_id, "/work/tool.html", cand["html"], client)
    missing = read_file_from_environment(env_id, DEFAULT_SCREENSHOT_PATH, client)
    present = read_file_from_environment(env_id, "/work/tool.html", client)
    with_body = read_file_from_environment(
        env_id, "/work/tool.html", client, include_contents=True
    )
    ok = True
    ok &= _check("write reports WROTE", "WROTE:" in wrote.output_text)
    ok &= _check("missing screenshot reports EXISTS false", "EXISTS: false" in missing.output_text)
    ok &= _check("written file reports EXISTS true", "EXISTS: true" in present.output_text)
    ok &= _check("contents read returns a BASE64 block", "BASE64:" in with_body.output_text)
    return ok


def test_output_cap_passed() -> bool:
    class RecordingInteractions:
        def __init__(self):
            self.seen = None

        def create(self, **kwargs):
            self.seen = kwargs

            class R:
                output_text = (
                    "```html\n<!doctype html><html><body>"
                    "<script>var x=1;</script></body></html>\n```\nRationale: ok.\n"
                )
                id = "int_rec"
                environment_id = kwargs.get("environment", "env_rec")
                steps = []

            return R()

    class RecordingClient:
        def __init__(self):
            self.interactions = RecordingInteractions()

    client = RecordingClient()
    create_interaction("hi", client)
    seen = client.interactions.seen
    cap = ("config" in seen) or ("max_output_tokens" in seen)
    return _check("create raises the output cap (config or max_output_tokens)", cap)


def test_scope_lock() -> bool:
    brief = "\n".join(
        [
            "User need: a minimal tip calculator",
            "Tool category: calculator",
            "Core interactions: ['Enter the bill amount', 'Pick a tip percent', 'Read the total']",
            "Data model: Last tip percent in localStorage.",
            "Success criteria: ['Changing inputs updates the total']",
        ]
    )
    cores = core_interactions_from_brief(brief)
    prompt = render_implementer_prompt(_STRATEGIES[1], brief, [], "#5B8DEF")
    ok = True
    ok &= _check("parses the core interactions", cores == [
        "Enter the bill amount", "Pick a tip percent", "Read the total"
    ])
    ok &= _check("prompt has a SCOPE LOCK section", "SCOPE LOCK" in prompt)
    ok &= _check("scope lock restates each interaction", all(c in prompt for c in cores))
    ok &= _check("scope lock forbids extras", "not on that list" in prompt or "nothing else" in prompt)
    ok &= _check("never list forbids stray features", "copy, share, summary" in prompt)
    ok &= _check("scope prompt has no em dash", not has_long_dash(prompt))
    return ok


def test_base64_write_roundtrip() -> bool:
    client = FakeManagedClient()
    impl = ManagedAgentsImplementer(client=client)
    cand = impl.build_candidate(_STRATEGIES[0], _BRIEF, _LESSONS)
    env_id = cand["environment_id"]
    write_file_to_environment(env_id, DEFAULT_TOOL_PATH, cand["html"], client)
    read = read_file_from_environment(env_id, DEFAULT_TOOL_PATH, client, include_contents=True)
    report = parse_file_report(read.output_text)
    import base64 as _b64

    decoded = _b64.b64decode(report["base64"]).decode("utf-8") if report["base64"] else ""
    ok = True
    ok &= _check("written file exists", report["exists"])
    ok &= _check("exact bytes round-trip through base64", decoded == cand["html"])
    return ok


def test_default_test_loads_file_url() -> bool:
    script = default_playwright_test(DEFAULT_TOOL_PATH, DEFAULT_SCREENSHOT_PATH)
    ok = True
    ok &= _check("default test loads the file url", "file://" + DEFAULT_TOOL_PATH in script)
    ok &= _check("default test screenshots to the path", DEFAULT_SCREENSHOT_PATH in script)
    ok &= _check("default test sets a 390px viewport", "390" in script)
    ok &= _check("default test prints a JSON result", "RESULT_JSON" in script)
    ok &= _check("default test has no em dash", not has_long_dash(script))
    return ok


def test_parse_reports() -> bool:
    run = "STDOUT:\nRESULT_JSON {\"loaded\": true}\nSTDERR:\n\nEXIT_CODE: 0\n"
    rep = parse_run_report(run)
    fil = parse_file_report("FILE: /work/screenshot.png\nEXISTS: true\nSIZE: 2048\n")
    ok = True
    ok &= _check("run report reads exit code", rep["exit_code"] == 0)
    ok &= _check("run report reads stdout", "RESULT_JSON" in rep["stdout"])
    ok &= _check("file report reads exists", fil["exists"] is True)
    ok &= _check("file report reads size", fil["size"] == 2048)
    return ok


def test_run_functionality_test() -> bool:
    client = FakeManagedClient()
    impl = ManagedAgentsImplementer(client=client)
    cand = impl.build_candidate(_STRATEGIES[0], _BRIEF, _LESSONS)
    result = run_functionality_test(cand["environment_id"], cand["html"], client=client)
    ok = True
    ok &= _check("test ran with exit code 0", result["exit_code"] == 0)
    ok &= _check("tool loaded in the sandbox", '"loaded": true' in result["stdout"])
    ok &= _check("screenshot was captured", result["screenshot_exists"])
    ok &= _check("screenshot path returned", result["screenshot_path"] == DEFAULT_SCREENSHOT_PATH)
    ok &= _check("screenshot has bytes", result["screenshot_size"] > 0)
    return ok


def main() -> int:
    tests = [
        ("extract", test_extract),
        ("accent_logic", test_accent_logic),
        ("em_dash", test_em_dash),
        ("prompt_assembly", test_prompt_assembly),
        ("scope_lock", test_scope_lock),
        ("build_one", test_build_one),
        ("build_parallel", test_build_parallel),
        ("reuse_sandbox", test_reuse_sandbox),
        ("sdk_fallback", test_sdk_fallback),
        ("completeness_checks", test_completeness_checks),
        ("extract_truncated", test_extract_truncated),
        ("guard_raises", test_guard_raises),
        ("guard_retry_recovers", test_guard_retry_recovers),
        ("file_io", test_file_io),
        ("output_cap_passed", test_output_cap_passed),
        ("base64_write_roundtrip", test_base64_write_roundtrip),
        ("default_test_loads_file_url", test_default_test_loads_file_url),
        ("parse_reports", test_parse_reports),
        ("run_functionality_test", test_run_functionality_test),
    ]
    all_ok = True
    for name, fn in tests:
        print(f"\n[{name}]")
        all_ok &= fn()
    print("\n" + ("ALL TESTS PASSED" if all_ok else "TESTS FAILED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
