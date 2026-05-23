"""Implementer prompt assembly. Mirrors the shared prompt contract and stays in
sync with it. One prompt per candidate, three strategy variants that share the
exact design tokens and differ only in layout, interaction structure, and
density, never in palette or typography.

The prompt is one self-contained string because the Managed Agents create call
takes a single `input`. It inlines shared/base.css verbatim, sets the chosen
accent, and forbids em dashes and any runtime network call.
"""
from __future__ import annotations

import ast
import re

from .config import BASE_CSS_PATH

# Appended to every prompt, same intent as core.prompts.GLOBAL_RULE.
GLOBAL_RULE = (
    "Never use em dashes or long dashes anywhere in your output, including the "
    "HTML, visible text, and code comments. Use hyphens with spaces. No "
    "marketing language. Plain, direct, concrete."
)

# Density and layout emphasis. This is the only axis on which candidates differ.
EMPHASIS_TEXT = {
    "speed_minimal": (
        "speed_minimal: the sparsest layout, the fastest path to the primary "
        "action, the least chrome. Strip everything that is not the hero and the "
        "one action."
    ),
    "polish": (
        "polish: the same tokens, considered detail and the restrained "
        "micro-interactions from the design system, slightly richer hierarchy. "
        "Still calm, never decorative."
    ),
    "minimal_whitespace": (
        "minimal_whitespace: maximize breathing room, one dominant action, the "
        "fewest visible controls. Generous negative space, nothing crowded."
    ),
}

# Per-category arrangement guidance from the shared design system. The tokens are fixed;
# only the arrangement varies.
CATEGORY_GUIDANCE = {
    "timer": "Hero clock dominates, one large Start or Pause, rounds as small chips.",
    "tracker": "Hero count, one big increment action at the bottom, history as a quiet muted list above.",
    "calculator": "Inputs at the top, the result as the hero value below, no clutter.",
    "converter": "Inputs at the top, the converted result as the hero value below, no clutter.",
    "flashcards": "Card centered, tap to flip with a 120ms cross-fade not a 3D spin, a thin progress bar.",
    "checklist": "Large tap rows, completed items fade to muted and move down, the primary action adds an item.",
    "decision_tool": "The choice surface centered, one decisive Pick action, result revealed with a 150ms fade.",
    "quiz": "One question centered, large answer targets, a thin progress bar, clear correct or wrong feedback.",
    "single_user_game": "The play surface centered, one decisive action, score as a quiet value, no clutter.",
    "log": "A quiet list of entries above, one clear add action at the bottom, newest first.",
    "randomizer": "The result surface centered, one decisive Pick or Roll action, result revealed with a 150ms fade.",
    "planner": "A quiet ordered list, one clear add action at the bottom, the next item emphasized.",
    "display_only": "The single most important value as the hero, supporting context muted beneath it.",
    "utility": "The single most important value or control as the hero, one clear action, nothing extra.",
}

_DEFAULT_GUIDANCE = (
    "One hero value, one clear primary action in the thumb zone, supporting "
    "detail muted. Nothing decorative."
)

_TOOL_CATEGORY_RE = re.compile(r"Tool category\s*:\s*(.+)", re.IGNORECASE)
_CORE_RE = re.compile(r"Core interactions\s*:\s*(\[.*?\])", re.IGNORECASE | re.DOTALL)


def tool_category_from_brief(brief: str) -> str:
    """Parse the tool category out of the orchestrator brief blob."""
    match = _TOOL_CATEGORY_RE.search(brief or "")
    if match:
        return match.group(1).strip().lower()
    return "utility"


def core_interactions_from_brief(brief: str) -> list:
    """Parse the core interactions list out of the orchestrator brief blob.

    The brief carries them as a Python list literal. Returns a list of strings,
    or an empty list if it cannot be parsed.
    """
    match = _CORE_RE.search(brief or "")
    if not match:
        return []
    try:
        value = ast.literal_eval(match.group(1))
    except (ValueError, SyntaxError):
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


def scope_block(brief: str) -> str:
    """Restate the plan's core interactions as the exact, only build scope."""
    cores = core_interactions_from_brief(brief)
    if cores:
        listed = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(cores))
        return "Build exactly these core interactions and nothing else:\n" + listed
    return (
        "Build exactly the core interactions listed in THE BUILD BRIEF above and "
        "nothing else."
    )


def load_base_css() -> str:
    """Read shared/base.css and inline it verbatim into each tool."""
    return BASE_CSS_PATH.read_text(encoding="utf-8")


def format_lessons(lessons: list) -> str:
    """Render retrieved UX lessons as a readable, applyable list."""
    if not lessons:
        return (
            "No prior lessons yet. Apply the design system and the hard "
            "constraints below with full care."
        )
    lines = []
    for item in lessons:
        lid = item.get("id", "lesson")
        text = (item.get("lesson_text") or "").strip()
        good = (item.get("good_pattern") or "").strip()
        line = f"- [{lid}] {text}"
        if good:
            line += f" Good pattern: {good}"
        lines.append(line)
    return "\n".join(lines)


def render_implementer_prompt(
    strategy: dict,
    brief: str,
    lessons: list,
    accent: str,
    *,
    tool_category: "str | None" = None,
    base_css: "str | None" = None,
) -> str:
    """Build the full single-string implementer prompt for one candidate."""
    cid = strategy.get("id", "A")
    framework = strategy.get("framework", "vanilla_html")
    emphasis = strategy.get("ux_emphasis", "speed_minimal")
    emphasis_text = EMPHASIS_TEXT.get(emphasis, EMPHASIS_TEXT["speed_minimal"])

    category = (tool_category or tool_category_from_brief(brief)).strip().lower()
    guidance = CATEGORY_GUIDANCE.get(category, _DEFAULT_GUIDANCE)

    css = base_css if base_css is not None else load_base_css()
    lessons_block = format_lessons(lessons)
    scope = scope_block(brief)

    return f"""You are Implementer {cid} for Oneline. You build ONE candidate personal tool: a single self-contained HTML file. The person who asked will use it on their own phone, then discard it. Market size is one. Lifetime may be days.

{GLOBAL_RULE}

THE BUILD BRIEF
{brief}

SCOPE LOCK (this overrides any instinct to be helpful)
{scope}
Implement each listed interaction, then stop. Do not invent or add anything that is not on that list: no extra buttons, controls, inputs, settings, modes, tabs, export, copy, share, summary, totals, history, presets, or "nice to have" features. If an idea is not in the list above, leave it out. A smaller tool that does exactly the listed interactions wins over a larger one with extras. Extra features are a defect here, not a bonus, and they bloat the file toward truncation. Keep the file as small as the listed interactions allow.

YOUR STRATEGY
Candidate id: {cid}
Framework label: {framework} (internal record only; your output is always one self-contained HTML file with inline CSS, never an external framework fetch)
Density and layout emphasis: {emphasis}

The three Oneline candidates share these exact tokens and differ ONLY in layout, interaction structure, and density, never in palette or typography. Build for your emphasis:
{emphasis_text}

UX LESSONS FROM EARLIER BUILDS (apply every one)
{lessons_block}

HARD CONSTRAINTS (behavior and scope)
- Build ONLY the core interactions in the scope lock above. Nothing extra.
- Mobile first, iPhone Safari at 390px width, used one-handed.
- Primary action in the bottom third of the screen, thumb reachable, at least 52px tall.
- Touch targets at least 44px.
- Single page, no routing. One self-contained HTML file with inline CSS and JS.
- localStorage only for state. No login, no auth, no backend.
- The ONLY external resource you may load is one optional web font from a CDN. Do not load Tailwind, any CSS or JS framework, analytics, or any other remote resource. No fetch, no XMLHttpRequest, no network calls at runtime.
- Loads in under 3 seconds.
- Concrete button text: a verb plus a noun naming the real action, like Start timer or Mark done or Roll again. Never Submit or Go.
- Visible feedback on every tap.
- No onboarding, no signup, no email capture, no marketing copy, no share or invite buttons. The user opens it and uses it.
- No em dashes or long dashes anywhere in the HTML, text, or comments. Use hyphens with spaces.

DESIGN SYSTEM (non-negotiable, you do not invent your own look)
Paste this CSS verbatim at the top of your <style>, then add only tool-specific layout rules built from these variables. Never hardcode a color or size that duplicates a token. Tools that invent their own palette or typography are rejected by the design judge.

{css}

ACCENT
Use exactly one accent, applied only to the primary action and the single most important live value. Everything else is grayscale from the tokens. The accent chosen for this tool is {accent}. Immediately after the pasted CSS, add this line so the accent is active:
:root {{ --accent: {accent}; }}
You may choose a different accent only from this approved set if it fits the tool better, and if so update both that line and your rationale: blue #5B8DEF, green #3FB950, amber #E3A008, violet #A371F7, red #F85149, teal #2DD4BF. Never use a hex outside this set. Never use more than one accent.

HERO
Exactly one hero element: the single most glanceable value, in var(--font-mono), 48px weight 700, centered. A timer's clock, a counter's count, a countdown's remaining value. Only one hero per tool.

LAYOUT GUIDANCE FOR THIS {category} TOOL (adapt the arrangement, keep the language)
{guidance}

NEVER (the design judge penalizes these hard)
- any feature, button, control, mode, export, copy, share, summary, or total that is not one of the core interactions in the scope lock above.
- decorative gradients, especially purple to pink. The base is flat dark.
- emoji as buttons or primary iconography.
- more than one accent in the tool.
- raw unstyled system controls next to styled ones.
- center-aligned body text. Only headings and the hero value center.
- light mode, rainbow fills, large high-saturation areas.
- any touch target under 44px.

OUTPUT
1. The complete HTML file in a single fenced code block opened with three backticks and the word html. The pasted token block included, dark base, one accent, exactly one hero, all spacing on the 8px grid.
2. After the code block, exactly one line that starts with "Rationale:" naming your accent choice and your single most important layout decision. No em dashes.
Output nothing else. No preamble, no explanation outside the rationale line.
"""
