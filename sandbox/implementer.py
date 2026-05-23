"""The Managed Agents implementer. Implements core.interfaces.ImplementerClient.

build_candidate(strategy, brief, lessons) -> Candidate spawns one isolated
managed sandbox, runs the implementer prompt with gemini-3.5-flash inside it,
extracts the single-file HTML, guarantees no em dash, and returns a Candidate
dict that matches shared/schemas/candidate.schema.json. The Candidate carries
the environment_id so the functionality judge can run Playwright in the same
sandbox the tool was built in.

build_candidates(strategies, brief, lessons) -> list[Candidate] spawns the three
sandboxes in parallel, one per strategy, and returns the three Candidates.

core injects an instance via orchestrator.make_default_deps(implementer=...).
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from . import client as client_mod
from .accents import recommend_accent
from .config import IMPLEMENTER_MODEL, MAX_OUTPUT_TOKENS
from .extract import (
    assert_no_em_dash,
    extract_accent,
    extract_html,
    extract_rationale,
    html_problems,
    strip_long_dashes,
)
from .prompts import load_base_css, render_implementer_prompt, tool_category_from_brief

# Keys allowed on a Candidate. The schema is additionalProperties:false, so we
# emit exactly these and nothing else.
_CANDIDATE_KEYS = (
    "candidate_id",
    "html",
    "environment_id",
    "steps",
    "rationale",
    "accent",
    "framework",
    "ux_emphasis",
)


def _warn(message: str) -> None:
    print(f"[sandbox] {message}", file=sys.stderr)


class IncompleteHTMLError(RuntimeError):
    """Raised when the managed agent returned a truncated or broken HTML file.

    Carries the candidate id and the specific structural problems so the caller
    can see why a Candidate was not returned (for example a missing closing
    script or body tag from output truncation).
    """

    def __init__(self, candidate_id: str, problems: list):
        self.candidate_id = candidate_id
        self.problems = problems
        super().__init__(
            f"candidate {candidate_id} returned incomplete HTML: "
            + "; ".join(problems)
        )


class ManagedAgentsImplementer:
    """Builds Oneline candidates in Gemini Managed Agents sandboxes."""

    def __init__(self, client=None, *, model: "str | None" = IMPLEMENTER_MODEL,
                 strict_dashes: bool = False, max_workers: int = 3,
                 max_output_tokens: "int | None" = MAX_OUTPUT_TOKENS,
                 verify_complete: bool = True, max_build_attempts: int = 2):
        # client is a google-genai client; left lazy so the object constructs
        # without an API key and is created on first build.
        self._client = client
        self.model = model
        self.strict_dashes = strict_dashes
        self.max_workers = max_workers
        # Raise the output cap so larger self-contained tools are not truncated.
        self.max_output_tokens = max_output_tokens
        # Guard against truncated HTML: verify completeness, retry, then raise.
        self.verify_complete = verify_complete
        self.max_build_attempts = max(1, max_build_attempts)
        # Read the shared base.css once and reuse it across candidates.
        self._base_css = load_base_css()

    def _client_or_default(self):
        if self._client is None:
            self._client = client_mod.get_client()
        return self._client

    def build_candidate(self, strategy: dict, brief: str, lessons: list) -> dict:
        """Build one candidate in its own managed sandbox. Returns a Candidate.

        The HTML is verified complete before a Candidate is returned. A truncated
        result (for example an unclosed script tag) triggers a rebuild up to
        max_build_attempts; if it never completes, IncompleteHTMLError is raised
        so a broken tool is never passed on.
        """
        cid = strategy.get("id", "A")
        category = tool_category_from_brief(brief)
        accent = recommend_accent(category, brief)

        prompt = render_implementer_prompt(
            strategy,
            brief,
            lessons,
            accent,
            tool_category=category,
            base_css=self._base_css,
        )

        interaction = None
        html = ""
        problems: list = ["no output"]
        for attempt in range(1, self.max_build_attempts + 1):
            interaction = client_mod.create_interaction(
                prompt, self._client_or_default(), model=self.model,
                max_output_tokens=self.max_output_tokens,
            )
            output_text = getattr(interaction, "output_text", "") or ""
            html = extract_html(output_text)
            problems = html_problems(html)
            if not problems:
                break
            _warn(
                f"candidate {cid}: incomplete HTML on attempt {attempt} of "
                f"{self.max_build_attempts} ({'; '.join(problems)})"
            )

        if problems and self.verify_complete:
            raise IncompleteHTMLError(cid, problems)

        output_text = getattr(interaction, "output_text", "") or ""
        rationale = extract_rationale(output_text)

        # Em dash ban is absolute. Verify, then sanitize before passing on. In
        # strict mode a stray em dash raises instead of being cleaned.
        if self.strict_dashes:
            assert_no_em_dash(html)
            assert_no_em_dash(rationale)
        else:
            html, n_html = strip_long_dashes(html)
            rationale, n_rat = strip_long_dashes(rationale)
            if n_html or n_rat:
                _warn(
                    f"candidate {cid}: stripped {n_html + n_rat} long dash(es) "
                    "from generated output (prompt forbids them)"
                )
        # Final guarantee that nothing with an em dash leaves this package.
        assert_no_em_dash(html)
        assert_no_em_dash(rationale)

        # The accent the model actually wrote wins; fall back to the recommended
        # one if it is missing or off-system. Always an approved hex.
        resolved_accent = extract_accent(html) or accent

        candidate = {
            "candidate_id": cid,
            "html": html,
            "environment_id": getattr(interaction, "environment_id", "") or "",
            "steps": client_mod.step_count(interaction),
            "rationale": rationale,
            "accent": resolved_accent,
            "framework": strategy.get("framework"),
            "ux_emphasis": strategy.get("ux_emphasis"),
        }
        return {k: candidate[k] for k in _CANDIDATE_KEYS if candidate.get(k) is not None}

    def build_candidates(self, strategies: list, brief: str, lessons: list) -> list:
        """Spawn one sandbox per strategy in parallel. Returns Candidates in the
        original strategy order. Each carries its own environment_id."""
        if not strategies:
            return []
        workers = min(self.max_workers, len(strategies))
        results: list = [None] * len(strategies)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self.build_candidate, strategy, brief, lessons): i
                for i, strategy in enumerate(strategies)
            }
            for future in futures:
                idx = futures[future]
                results[idx] = future.result()
        return results
