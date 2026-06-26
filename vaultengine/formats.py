"""Input formats — decide which regions of a document get scrubbed.

`plain` scrubs everything. `markdown` scrubs the prose but leaves fenced
``` code blocks untouched — so an embedded JSON schema, code sample, or output
template you include for the model is preserved verbatim instead of being
mangled by pseudonymization.

A "segment plan" is a list of ``(kind, content)`` where kind is ``'keep'`` or
``'scrub'``; the concatenation of all contents always reproduces the input
exactly.
"""

from __future__ import annotations

from typing import List, Tuple

Segment = Tuple[str, str]

PLAIN = "plain"
MARKDOWN = "markdown"
AUTO = "auto"
FORMATS = (PLAIN, MARKDOWN, AUTO)

_FENCE = "```"


def detect_format(text: str) -> str:
    """A fenced code block is the signal to switch on `markdown` protection."""
    return MARKDOWN if (text and _FENCE in text) else PLAIN


def _split_fences(s: str) -> List[Segment]:
    """Keep fenced ``` blocks verbatim; everything else is scrubbable."""
    out: List[Segment] = []
    i = 0
    while True:
        start = s.find(_FENCE, i)
        if start == -1:
            if s[i:]:
                out.append(("scrub", s[i:]))
            break
        if s[i:start]:
            out.append(("scrub", s[i:start]))
        end = s.find(_FENCE, start + 3)
        if end == -1:                      # unterminated fence: keep the rest
            out.append(("keep", s[start:]))
            break
        end += 3
        out.append(("keep", s[start:end]))
        i = end
    return out


def segment(text: str, fmt: str = AUTO) -> List[Segment]:
    if fmt == AUTO:
        fmt = detect_format(text)
    if fmt == MARKDOWN:
        return _split_fences(text)
    return [("scrub", text)]
