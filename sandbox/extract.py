"""Pull the parts of a Candidate out of the implementer's text output, and
guarantee no long dash ever leaves this package.

The implementer is told to return the complete HTML in a single ```html block
followed by one line that starts with "Rationale:". These helpers extract that
HTML and rationale, find the active --accent the model wrote, and strip any long
dash that slipped past the prompt. The em dash ban is absolute across the repo:
we verify and sanitize before passing anything downstream.

The long-dash characters are built with chr() on purpose so this source file
itself contains no long-dash byte and stays clean under the repo lint.
"""
from __future__ import annotations

import re

from .accents import normalize_accent

# The long-dash family by code point. The em dash (U+2014) is the headline
# offender; we also catch its relatives so none reach the generated HTML. The
# em dash replacement keeps the repo rule "hyphen with spaces"; the rest map to
# a plain hyphen.
EM_DASH = chr(0x2014)
LONG_DASHES = {
    chr(0x2014): " - ",  # em dash
    chr(0x2015): " - ",  # horizontal bar
    chr(0x2013): "-",    # en dash
    chr(0x2012): "-",    # figure dash
    chr(0x2212): "-",    # minus sign
}

_HTML_FENCE = re.compile(r"```(?:html)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_OPEN_FENCE = re.compile(r"```[ \t]*html[ \t]*\r?\n", re.IGNORECASE)
_DOCTYPE = re.compile(r"(<!doctype html.*?</html>)", re.DOTALL | re.IGNORECASE)
_DOCTYPE_OPEN = re.compile(r"<!doctype html", re.IGNORECASE)
_HTML_TAG = re.compile(r"(<html.*?</html>)", re.DOTALL | re.IGNORECASE)
_HTML_OPEN = re.compile(r"<html[\s>]", re.IGNORECASE)
_RATIONALE = re.compile(r"^\s*Rationale\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
# The active accent is the last --accent declaration in source order; CSS lets a
# later :root override the base default. We never match --accent-blue and friends.
_ACCENT = re.compile(r"--accent\s*:\s*(#[0-9A-Fa-f]{3,8})\s*[;}]")


def has_long_dash(text: str) -> bool:
    """True if any long dash (em, en, bar, figure, minus) is present."""
    return any(d in (text or "") for d in LONG_DASHES)


def strip_long_dashes(text: str) -> "tuple[str, int]":
    """Replace every long dash with a hyphen form. Returns (clean, count)."""
    if not text:
        return text or "", 0
    count = sum(text.count(d) for d in LONG_DASHES)
    clean = text
    for bad, good in LONG_DASHES.items():
        clean = clean.replace(bad, good)
    return clean, count


def assert_no_em_dash(text: str) -> None:
    """Raise if an em dash remains. The last line of defence."""
    if EM_DASH in (text or ""):
        idx = text.index(EM_DASH)
        raise ValueError(
            f"em dash (U+2014) found at index {idx} in generated output; "
            "hyphens only is an absolute rule"
        )


def _strip_trailing_fence(chunk: str) -> str:
    """Trim trailing whitespace and a dangling closing code fence, if any."""
    out = (chunk or "").rstrip()
    if out.endswith("```"):
        out = out[:-3].rstrip()
    return out


def extract_html(output_text: str) -> str:
    """Return the HTML document from the implementer output, even if truncated.

    Order: a properly closed ```html block; an UNCLOSED opening fence (the
    truncation case) taking everything after it; a doctype-to-/html span, or
    doctype-to-end if unclosed; an <html>...</html> span, or <html>-to-end if
    unclosed; finally the raw text. Capturing the partial body lets the
    completeness guard flag it instead of shipping the code-fence wrapper.
    """
    text = output_text or ""
    fence = _HTML_FENCE.search(text)
    if fence and fence.group(1).strip():
        return fence.group(1).strip()
    open_fence = _OPEN_FENCE.search(text)
    if open_fence:
        return _strip_trailing_fence(text[open_fence.end():])
    doc = _DOCTYPE.search(text)
    if doc:
        return doc.group(1).strip()
    doc_open = _DOCTYPE_OPEN.search(text)
    if doc_open:
        return _strip_trailing_fence(text[doc_open.start():])
    tag = _HTML_TAG.search(text)
    if tag:
        return tag.group(1).strip()
    html_open = _HTML_OPEN.search(text)
    if html_open:
        return _strip_trailing_fence(text[html_open.start():])
    return text.strip()


def html_problems(html: str) -> list:
    """Structural problems that mark incomplete or truncated HTML.

    An empty list means the document looks complete. Catches the truncation
    symptoms seen in live runs: an unclosed script tag, a missing closing body
    or html tag, and an unbalanced style block.
    """
    problems: list = []
    text = html or ""
    low = text.lower()
    if not low.strip():
        return ["empty output"]

    if "<html" not in low:
        problems.append("missing opening <html>")
    if "</html>" not in low:
        problems.append("missing closing </html>")
    if "<body" in low and "</body>" not in low:
        problems.append("missing closing </body>")

    open_scripts = len(re.findall(r"<script\b", low))
    close_scripts = len(re.findall(r"</script\s*>", low))
    if open_scripts != close_scripts:
        problems.append(
            f"unbalanced script tags ({open_scripts} open, {close_scripts} close)"
        )

    open_styles = len(re.findall(r"<style\b", low))
    close_styles = len(re.findall(r"</style\s*>", low))
    if open_styles != close_styles:
        problems.append(
            f"unbalanced style tags ({open_styles} open, {close_styles} close)"
        )
    return problems


def is_html_complete(html: str) -> bool:
    """True if the HTML has no structural completeness problems."""
    return not html_problems(html)


def extract_rationale(output_text: str) -> str:
    """Return the one-line rationale, or a neutral fallback if absent."""
    text = output_text or ""
    # Look outside any fenced code block so a comment inside the HTML is ignored.
    outside = _HTML_FENCE.sub("", text)
    match = _RATIONALE.search(outside) or _RATIONALE.search(text)
    if match:
        return "Rationale: " + match.group(1).strip()
    return "Rationale: candidate built to the Oneline design system."


def extract_accent(html: str) -> "str | None":
    """Return the canonical approved accent written into the HTML, or None.

    Takes the last --accent declaration in source order, which is the value that
    actually paints, then validates it against the approved set.
    """
    matches = _ACCENT.findall(html or "")
    for raw in reversed(matches):
        accent = normalize_accent(raw)
        if accent:
            return accent
    return None
