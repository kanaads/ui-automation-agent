"""Parses Playwright's `Locator.aria_snapshot(mode="ai")` output into
`ObservedNode`s.

That output is a YAML-ish indented tree, two spaces per level, of lines
shaped like:

    - role "optional accessible name" [attr=value] [flag] [ref=xxx]:

with one special leaf form, a link's destination:

    - /url: /some/path

and one more leaf form worth calling out explicitly, since it looks
like the branch syntax but isn't one: a node with no accessible *name*
attribute but real rendered text still gets that text inline after the
colon, unquoted --

    - generic [ref=f2e4]: No records match your search.

confirmed live against the target app's own "no such member" banner
(rendered as a nameless `<font><b>` span): this is not a child node
list, it is that generic's own name, just spelled without the quotes
`_NODE_RE` otherwise expects. Treated as the node's `name` whenever a
quoted one wasn't already captured.

Chosen over the older `Page.accessibility.snapshot()` API (removed in
the Playwright version this project pins) precisely because `mode="ai"`
hands back a stable `ref` that a same-process `locator("aria-ref=...")`
call can act on later -- refs are the seam between "what we observed"
and "what we can act on."

One deliberate deviation from a literal transcription: a same-origin
`iframe` node's own accessible subtree is recursed into by Chromium's
AX tree and shows up nested right here in the *parent* frame's
snapshot -- confirmed live against the target app's shell page, which
produced the child frame's own heading/textbox/button nodes a second
time, under the SAME refs, inside the main frame's text. Since
`WebSurface.observe()` (Phase 3) already calls `aria_snapshot()`
separately for every named frame to get correct, unambiguous `frame`
labels, keeping a recursed-into iframe's descendants here as well would
silently double every control inside it -- which is exactly what made
`resolve_target` (Phase 4) report a same-name button as AMBIGUOUS the
first time this parser was pointed at a page with real nested iframes
rather than a bare fragment page. So this parser keeps the `iframe`
node itself (a useful landmark) but discards every line nested under
it; that content is captured once, correctly labeled, when the caller
snapshots that frame directly.
"""
from __future__ import annotations

import re

from cua.surface.models import ObservedNode

_NODE_RE = re.compile(
    r'^(?P<role>[^\s"\[:]+)'
    r'(?:\s+"(?P<name>(?:[^"\\]|\\.)*)")?'
    r"(?P<attrs>(?:\s*\[[^\]]*\])*)"
    r"\s*:?"
    r"(?:\s+(?P<text>.+))?"
    r"\s*$"
)
_ATTR_RE = re.compile(r"\[([^\]]*)\]")
_URL_RE = re.compile(r"^/url:\s*(.*)$")


def _parse_attrs(attrs_str: str) -> dict[str, object]:
    attrs: dict[str, object] = {}
    for raw in _ATTR_RE.findall(attrs_str):
        if "=" in raw:
            key, _, value = raw.partition("=")
            attrs[key.strip()] = value.strip()
        else:
            attrs[raw.strip()] = True
    return attrs


def parse_aria_snapshot(text: str, *, frame: str) -> list[ObservedNode]:
    """Parse one frame's aria_snapshot text into a flat list of nodes
    with depth/parent_ref set from indentation. `frame` is stamped onto
    every node so a caller merging multiple frames' snapshots can still
    tell them apart (and so lookups stay scoped to `(frame, ref)`)."""
    nodes: list[ObservedNode] = []
    stack: list[tuple[int, ObservedNode]] = []  # (indent, node), shallowest last removed
    skip_below: int | None = None  # set to an iframe's indent while discarding its recursed-into subtree

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue

        stripped = raw_line.lstrip(" ")
        indent = len(raw_line) - len(stripped)

        if skip_below is not None:
            if indent > skip_below:
                continue  # inside a same-origin iframe's duplicated subtree -- see module docstring
            skip_below = None

        if not stripped.startswith("- "):
            continue  # tolerate stray/blank formatting rather than crashing
        content = stripped[2:]

        url_match = _URL_RE.match(content)
        if url_match:
            # Metadata for the most recently emitted node (its "child" by
            # indentation), not a node of its own.
            if stack:
                stack[-1][1].attrs["href"] = url_match.group(1).strip()
            continue

        match = _NODE_RE.match(content)
        if not match:
            continue  # tolerate a line we don't recognize rather than crashing

        attrs = _parse_attrs(match.group("attrs"))
        ref_value = attrs.pop("ref", None)
        ref = ref_value if isinstance(ref_value, str) else None
        name = match.group("name")
        if name is None and match.group("text") is not None:
            name = match.group("text").strip()

        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent_ref = stack[-1][1].ref if stack else None
        depth = len(stack)

        node = ObservedNode(
            ref=ref,
            frame=frame,
            role=match.group("role"),
            name=name,
            attrs=attrs,
            depth=depth,
            parent_ref=parent_ref,
        )
        nodes.append(node)
        stack.append((indent, node))

        if node.role == "iframe":
            skip_below = indent

    return nodes
