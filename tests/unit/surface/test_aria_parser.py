"""Parses Playwright's `aria_snapshot(mode="ai")` output -- a YAML-ish
tree of `- role "name" [attr=val] [flag] [ref=xxx]:` lines -- into
structured ObservedNode objects with parent/depth tracking. Pure string
processing, verified against real captures from the target app (see the
literal fixtures below, taken from an actual Chromium run) rather than
invented syntax, since getting this parser wrong would silently corrupt
everything built on top of it.

No browser involved here -- that's what makes this a `unit` test; the
real end-to-end capture-then-parse path is verified in
tests/integration/surface/test_web_surface.py.
"""
import pytest

from cua.surface.aria_parser import parse_aria_snapshot

pytestmark = pytest.mark.unit


def test_empty_text_yields_no_nodes():
    assert parse_aria_snapshot("", frame="main") == []


def test_single_node_with_name_and_ref():
    text = '- button "Search" [ref=f2e13]'
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    assert len(nodes) == 1
    node = nodes[0]
    assert node.role == "button"
    assert node.name == "Search"
    assert node.ref == "f2e13"
    assert node.frame == "contentFrame"
    assert node.depth == 0
    assert node.parent_ref is None


def test_node_without_a_name():
    text = "- textbox [ref=f2e10]"
    node = parse_aria_snapshot(text, frame="contentFrame")[0]
    assert node.role == "textbox"
    assert node.name is None
    assert node.ref == "f2e10"


def test_bracket_key_value_attr_is_captured():
    text = '- heading "Member Detail" [level=2] [ref=e3]'
    node = parse_aria_snapshot(text, frame="contentFrame")[0]
    assert node.attrs.get("level") == "2"


def test_bracket_boolean_flag_attr_is_captured():
    text = '- generic [active] [ref=e2]'
    node = parse_aria_snapshot(text, frame="contentFrame")[0]
    assert node.attrs.get("active") is True


def test_multiple_bracket_attrs_on_one_node():
    text = '- link "Open Sub-Account" [ref=e16] [cursor=pointer]'
    node = parse_aria_snapshot(text, frame="contentFrame")[0]
    assert node.attrs.get("cursor") == "pointer"
    assert node.ref == "e16"


def test_nested_children_get_correct_depth_and_parent():
    text = (
        '- document [ref=e1]:\n'
        '  - generic [ref=e2]:\n'
        '    - heading "Member Detail" [level=2] [ref=e3]\n'
    )
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    by_ref = {n.ref: n for n in nodes}
    assert by_ref["e1"].depth == 0
    assert by_ref["e1"].parent_ref is None
    assert by_ref["e2"].depth == 1
    assert by_ref["e2"].parent_ref == "e1"
    assert by_ref["e3"].depth == 2
    assert by_ref["e3"].parent_ref == "e2"


def test_siblings_at_the_same_depth_share_a_parent():
    text = (
        '- table [ref=e4]:\n'
        '  - rowgroup [ref=e5]:\n'
        '    - row [ref=e6]:\n'
        '      - cell "Member Name:" [ref=e7]\n'
        '      - cell "Alice Testperson" [ref=e8]\n'
    )
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    by_ref = {n.ref: n for n in nodes}
    assert by_ref["e7"].parent_ref == "e6"
    assert by_ref["e8"].parent_ref == "e6"
    assert by_ref["e7"].depth == by_ref["e8"].depth


def test_dedents_back_up_after_a_deep_branch():
    """A classic tree-parsing edge case: after descending into one
    subtree, a sibling at a shallower depth must pop the stack correctly
    rather than being attached under the wrong parent."""
    text = (
        '- row [ref=r1]:\n'
        '  - cell "Member Name:" [ref=c1]\n'
        '  - cell "Alice Testperson" [ref=c2]\n'
        '- row [ref=r2]:\n'
        '  - cell "Savings Balance:" [ref=c3]\n'
        '  - cell "$4,231.50" [ref=c4]\n'
    )
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    by_ref = {n.ref: n for n in nodes}
    assert by_ref["r1"].depth == 0
    assert by_ref["r2"].depth == 0
    assert by_ref["r2"].parent_ref is None
    assert by_ref["c3"].parent_ref == "r2"
    assert by_ref["c4"].parent_ref == "r2"


def test_url_metadata_line_attaches_as_href_not_a_new_node():
    text = (
        '- link "Open Sub-Account" [ref=e16] [cursor=pointer]:\n'
        '  - /url: /content/subaccount/new?id=10001\n'
    )
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    assert len(nodes) == 1  # the /url line must not become its own node
    link = nodes[0]
    assert link.role == "link"
    assert link.attrs.get("href") == "/content/subaccount/new?id=10001"


def test_combobox_with_option_children_captures_all_nodes():
    text = (
        '- cell "Savings" [ref=f1e9]:\n'
        '  - combobox [ref=f1e10]:\n'
        '    - option "Savings" [selected]\n'
        '    - option "Checking"\n'
    )
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    roles = [n.role for n in nodes]
    assert roles == ["cell", "combobox", "option", "option"]
    options = [n for n in nodes if n.role == "option"]
    assert options[0].name == "Savings"
    assert options[0].attrs.get("selected") is True
    assert options[1].name == "Checking"


def test_full_realistic_capture_from_the_search_page():
    """A literal capture from a real run against the target app --
    guards against the parser drifting from what Playwright actually
    emits, not just from hand-written fixtures."""
    text = (
        '- document [ref=f2e1]:\n'
        '  - generic [ref=f2e2]:\n'
        '    - heading "Member Search" [level=2] [ref=f2e3]\n'
        '    - table [ref=f2e5]:\n'
        '      - rowgroup [ref=f2e6]:\n'
        '        - row [ref=f2e7]:\n'
        '          - cell "Member Number:" [ref=f2e8]\n'
        '          - cell [ref=f2e9]:\n'
        '            - textbox [ref=f2e10]\n'
        '        - row [ref=f2e11]:\n'
        '          - cell [ref=f2e12]:\n'
        '            - button "Search" [ref=f2e13]\n'
    )
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    # document, generic, heading, table, rowgroup, 2x(row, cell, [cell]) minus
    # symmetry -- just count roles directly rather than a magic number.
    assert [n.role for n in nodes] == [
        "document",
        "generic",
        "heading",
        "table",
        "rowgroup",
        "row",
        "cell",
        "cell",
        "textbox",
        "row",
        "cell",
        "button",
    ]
    textbox = next(n for n in nodes if n.role == "textbox")
    assert textbox.name is None  # deliberately hostile: no accessible name
    assert textbox.parent_ref == "f2e9"
    button = next(n for n in nodes if n.role == "button")
    assert button.name == "Search"
    assert all(n.frame == "contentFrame" for n in nodes)


def test_blank_lines_between_nodes_are_tolerated():
    text = '- button "A" [ref=e1]\n\n- button "B" [ref=e2]\n'
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    assert [n.name for n in nodes] == ["A", "B"]


def test_a_line_not_starting_with_dash_is_tolerated_not_fatal():
    """Defensive: any stray non-`- ` line (e.g. odd wrapping) should be
    skipped rather than raising, since a parser crash would take down
    perception entirely rather than just losing one node."""
    text = 'not a node line at all\n- button "A" [ref=e1]\n'
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    assert [n.name for n in nodes] == ["A"]


def test_a_dash_prefixed_line_that_still_fails_to_parse_as_a_node_is_tolerated():
    """Distinct from the 'no leading dash at all' case above: this line
    *does* start with '- ' (so it reaches _NODE_RE) but has no role
    text before the colon at all, so _NODE_RE itself can't match --
    still tolerated rather than raising."""
    text = '- : orphaned colon\n- button "A" [ref=e1]\n'
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    assert [n.name for n in nodes] == ["A"]


def test_node_missing_a_ref_is_still_parsed_with_ref_none():
    """Defensive: default-mode snapshots (no refs) shouldn't crash the
    parser even though WebSurface always requests mode='ai'."""
    text = '- button "Search"'
    node = parse_aria_snapshot(text, frame="contentFrame")[0]
    assert node.ref is None
    assert node.name == "Search"


def test_unquoted_inline_text_after_colon_becomes_the_node_name():
    """A literal capture from the target app's real 'no such member'
    banner: a nameless generic span's rendered text comes back inline
    after the colon, unquoted -- not a child-node list, even though the
    trailing colon looks exactly like the branch syntax everywhere
    else in this file."""
    text = "- generic [ref=f2e4]: No records match your search."
    node = parse_aria_snapshot(text, frame="contentFrame")[0]
    assert node.role == "generic"
    assert node.name == "No records match your search."
    assert node.ref == "f2e4"


def test_unquoted_inline_text_leaf_has_no_children_of_its_own():
    text = (
        '- paragraph [ref=e2]:\n'
        '  - generic [ref=e3]: No records match your search.\n'
        '- heading "Member Search" [ref=e5]\n'
    )
    nodes = parse_aria_snapshot(text, frame="contentFrame")
    by_ref = {n.ref: n for n in nodes}
    assert by_ref["e3"].parent_ref == "e2"
    assert by_ref["e5"].parent_ref is None  # correctly dedented, not swallowed as e3's child
    assert by_ref["e5"].depth == 0


def test_a_bare_branch_colon_with_no_trailing_text_still_has_no_name():
    """Guards against the new optional trailing-text group accidentally
    swallowing part of a normal branch line that just ends in ':'."""
    text = "- document [ref=e1]:"
    node = parse_aria_snapshot(text, frame="contentFrame")[0]
    assert node.name is None


def test_iframe_children_are_discarded_but_the_iframe_node_itself_is_kept():
    """A literal capture from the real shell page's main frame: a
    same-origin iframe's accessible subtree is recursed into by
    Chromium and shows up right here, a second time, under the SAME
    refs the child frame's own snapshot independently reports.
    WebSurface.observe() already snapshots every named frame directly,
    so keeping this recursed-into copy would make every control inside
    an iframe report as ambiguous (two candidates, one per frame) the
    moment a real page has one -- discovered live via exactly this
    shape, not invented."""
    text = (
        '- document [ref=e1]:\n'
        '  - table [ref=e3]:\n'
        '    - rowgroup [ref=e4]:\n'
        '      - row [ref=e5]:\n'
        '        - cell [ref=e6]:\n'
        '          - iframe [ref=e7]:\n'
        '            - generic [ref=f1e1]: Meridian Core Credit Union\n'
        '      - row [ref=e8]:\n'
        '        - cell [ref=e9]:\n'
        '          - iframe [ref=e10]:\n'
        '            - generic [ref=f2e1]:\n'
        '              - heading "Member Search" [level=2] [ref=f2e2]\n'
        '              - button "Search" [ref=f2e12]\n'
    )
    nodes = parse_aria_snapshot(text, frame="main")
    by_ref = {n.ref: n for n in nodes}

    assert set(by_ref) == {"e1", "e3", "e4", "e5", "e6", "e7", "e8", "e9", "e10"}
    assert by_ref["e7"].role == "iframe"
    assert by_ref["e10"].role == "iframe"
    # the iframe is a leaf here even though its own subtree had content
    assert not any(n.parent_ref in ("e7", "e10") for n in nodes)


def test_a_sibling_after_an_iframe_at_the_same_indent_is_still_parsed():
    """The skip must end exactly at the iframe's own indent -- a
    following sibling (not a descendant) is a real, distinct node."""
    text = (
        '- row [ref=e5]:\n'
        '  - iframe [ref=e7]:\n'
        '    - generic [ref=f1e1]: inside the iframe\n'
        '  - cell "after" [ref=e9]\n'
    )
    nodes = parse_aria_snapshot(text, frame="main")
    by_ref = {n.ref: n for n in nodes}
    assert "f1e1" not in by_ref
    assert by_ref["e9"].parent_ref == "e5"
    assert by_ref["e9"].role == "cell"


def test_an_ancestor_line_after_an_iframe_pops_the_stack_correctly():
    """The skip-then-resume must not corrupt depth/parent tracking for
    what comes after -- a line shallower than the iframe (not just
    equal) must still attach to the right ancestor."""
    text = (
        '- document [ref=e1]:\n'
        '  - row [ref=e5]:\n'
        '    - iframe [ref=e7]:\n'
        '      - generic [ref=f1e1]: inside\n'
        '  - row [ref=e8]:\n'
    )
    nodes = parse_aria_snapshot(text, frame="main")
    by_ref = {n.ref: n for n in nodes}
    assert "f1e1" not in by_ref
    assert by_ref["e8"].parent_ref == "e1"
    assert by_ref["e8"].depth == 1
