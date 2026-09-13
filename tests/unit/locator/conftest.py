"""Synthetic Observation fixtures that mirror the *real* node shape
captured live from the target app in Phase 3 -- a row is
`row -> [cell(label text), cell -> control]`, not a flat list of
labeled inputs. Getting the fixture shape right matters here: a
label-proximity resolver that only works against an idealized flat
structure would pass its own tests and still fail against the actual
hostile app.
"""
from __future__ import annotations

import pytest

from cua.surface.models import Observation, ObservedNode


def node(ref, frame, role, name=None, parent_ref=None, depth=0, **attrs) -> ObservedNode:
    return ObservedNode(ref=ref, frame=frame, role=role, name=name, attrs=attrs, depth=depth, parent_ref=parent_ref)


@pytest.fixture()
def search_page_observation() -> Observation:
    """Mirrors the real 'contentFrame' capture from /content/search:
    a row with a label cell ('Member Number:') and a sibling cell
    containing an unnamed textbox, plus a second row whose cell
    contains a named 'Search' button.
    """
    nodes = [
        node("e1", "contentFrame", "document"),
        node("e2", "contentFrame", "generic", parent_ref="e1", depth=1),
        node("e3", "contentFrame", "heading", "Member Search", parent_ref="e2", depth=2),
        node("e5", "contentFrame", "table", parent_ref="e2", depth=2),
        node("e6", "contentFrame", "rowgroup", parent_ref="e5", depth=3),
        node("e7", "contentFrame", "row", parent_ref="e6", depth=4),
        node("e8", "contentFrame", "cell", "Member Number:", parent_ref="e7", depth=5),
        node("e9", "contentFrame", "cell", parent_ref="e7", depth=5),
        node("e10", "contentFrame", "textbox", None, parent_ref="e9", depth=6),
        node("e11", "contentFrame", "row", parent_ref="e6", depth=4),
        node("e12", "contentFrame", "cell", parent_ref="e11", depth=5),
        node("e13", "contentFrame", "button", "Search", parent_ref="e12", depth=6),
    ]
    return Observation(nodes=nodes, url="http://x/content/search", title="t")


@pytest.fixture()
def detail_page_observation() -> Observation:
    """Mirrors /content/detail: non-interactive cells carry their text
    as `name`, which is what makes them extractable via label proximity
    without any id/test-id at all."""
    nodes = [
        node("e1", "contentFrame", "document"),
        node("e4", "contentFrame", "table", parent_ref="e1", depth=1),
        node("e5", "contentFrame", "rowgroup", parent_ref="e4", depth=2),
        node("e6", "contentFrame", "row", parent_ref="e5", depth=3),
        node("e7", "contentFrame", "cell", "Member Name:", parent_ref="e6", depth=4),
        node("e8", "contentFrame", "cell", "Alice Testperson", parent_ref="e6", depth=4),
        node("e9", "contentFrame", "row", parent_ref="e5", depth=3),
        node("e10", "contentFrame", "cell", "Savings Balance:", parent_ref="e9", depth=4),
        node("e11", "contentFrame", "cell", "$4,231.50", parent_ref="e9", depth=4),
    ]
    return Observation(nodes=nodes, url="http://x/content/detail", title="t")
