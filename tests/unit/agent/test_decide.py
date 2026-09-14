"""cua.agent.decide: the strict, provider-agnostic contract for one
LLM turn. `parse_agent_decision` never guesses -- a response that isn't
exactly one valid JSON decision (whatever the reason: bad JSON, a
missing field, an inconsistent field for the given action) raises
`AgentDecisionError` rather than being coerced into "probably meant
this," mirroring how `cua.locator.resolve_target` never guesses at an
ambiguous match. `cua.agent.discover` is what turns that exception into
a clean STUCK outcome (test_discover.py).
"""
import pytest

from cua.agent.decide import (
    AgentDecision,
    AgentDecisionError,
    _find_balanced_json_objects,
    parse_agent_decision,
)

pytestmark = pytest.mark.unit


def test_parses_a_clean_click_decision():
    raw = '{"thought": "search button is visible", "action": "click", "frame": "contentFrame", "ref": "e13"}'

    decision = parse_agent_decision(raw)

    assert decision == AgentDecision(thought="search button is visible", action="click", frame="contentFrame", ref="e13")


def test_parses_a_decision_wrapped_in_a_markdown_json_fence():
    raw = '```json\n{"thought": "t", "action": "click", "frame": "main", "ref": "b1"}\n```'

    decision = parse_agent_decision(raw)

    assert decision.action == "click"
    assert decision.ref == "b1"


def test_parses_a_decision_wrapped_in_a_bare_markdown_fence():
    raw = '```\n{"thought": "t", "action": "click", "frame": "main", "ref": "b1"}\n```'

    decision = parse_agent_decision(raw)

    assert decision.ref == "b1"


def test_parses_a_decision_with_leading_and_trailing_prose():
    raw = 'Sure, here is my decision:\n{"thought": "t", "action": "click", "frame": "main", "ref": "b1"}\nLet me know if that works.'

    decision = parse_agent_decision(raw)

    assert decision.ref == "b1"


@pytest.mark.parametrize(
    ("action", "kwargs"),
    [
        ("navigate", {"value": "/app?start=/content/search"}),
        ("click", {"frame": "main", "ref": "b1"}),
        ("type", {"frame": "main", "ref": "t1", "value": "10001"}),
        ("select", {"frame": "main", "ref": "s1", "value": "SAVINGS"}),
        ("wait_for", {"frame": "main", "ref": "h1"}),
        ("extract", {"frame": "main", "ref": "c1", "output_field": "balance_text"}),
        ("assert_checkpoint", {"frame": "main", "ref": "h1"}),
        ("dismiss", {"frame": "main", "ref": "x1"}),
        ("done", {}),
        ("stuck", {"reason": "no visible way to proceed"}),
    ],
)
def test_every_action_shape_parses_when_well_formed(action, kwargs):
    payload = {"thought": "t", "action": action, **kwargs}
    import json

    decision = parse_agent_decision(json.dumps(payload))

    assert decision.action == action


def test_not_json_at_all_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision("I think I should click the search button.")


def test_valid_json_but_not_an_object_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('["click", "main", "b1"]')


def test_unknown_action_value_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "scroll", "frame": "main", "ref": "b1"}')


def test_extra_unknown_field_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "click", "frame": "main", "ref": "b1", "extra": "nope"}')


def test_click_missing_frame_or_ref_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "click", "frame": "main"}')


def test_navigate_with_a_frame_and_ref_raises_agent_decision_error():
    """navigate takes a destination, never a (frame, ref) -- same
    shape rule Step._validate_shape already enforces on the artifact
    side (cua.artifact.models); the decision contract mirrors it."""
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "navigate", "value": "/x", "frame": "main", "ref": "b1"}')


def test_type_without_a_value_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "type", "frame": "main", "ref": "t1"}')


def test_extract_without_an_output_field_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "extract", "frame": "main", "ref": "c1"}')


def test_click_with_a_stray_output_field_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "click", "frame": "main", "ref": "b1", "output_field": "x"}')


def test_done_with_a_frame_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "done", "frame": "main"}')


def test_multiple_json_looking_fragments_in_prose_uses_the_first_balanced_one():
    raw = 'considering {"not": "this one"} vs {"thought": "t", "action": "click", "frame": "main", "ref": "b1"}'

    decision = parse_agent_decision(raw)

    assert decision.action == "click"


def test_navigate_without_a_value_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "navigate"}')


def test_navigate_with_a_stray_output_field_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "navigate", "value": "/x", "output_field": "x"}')


def test_click_with_a_stray_value_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "click", "frame": "main", "ref": "b1", "value": "nope"}')


def test_stuck_without_a_reason_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "stuck"}')


def test_stuck_with_a_blank_reason_raises_agent_decision_error():
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "stuck", "reason": "   "}')


def test_explicit_null_reason_on_a_non_terminal_action_parses_the_same_as_omitted():
    """A real model (observed live, Bedrock Claude Haiku 4.5) sends an
    explicit `"reason": null` on a non-terminal action rather than
    omitting the field entirely -- both are "no reason given," and only
    `stuck` ever requires a real one, so this must not be treated any
    differently than the field being absent."""
    with_null = parse_agent_decision(
        '{"thought": "t", "action": "click", "frame": "main", "ref": "b1", "reason": null}'
    )
    omitted = parse_agent_decision('{"thought": "t", "action": "click", "frame": "main", "ref": "b1"}')

    assert with_null == omitted
    assert with_null.reason == ""


def test_explicit_null_reason_on_stuck_still_raises_agent_decision_error():
    """`null` is "no reason given," same as omitting the field -- so it
    must fail exactly like the already-covered omitted/blank cases
    above, not be treated as some third, more-permissive shape."""
    with pytest.raises(AgentDecisionError):
        parse_agent_decision('{"thought": "t", "action": "stuck", "reason": null}')


def test_balanced_json_object_scanning_handles_escaped_quotes_and_backslashes():
    """A JSON string value can legitimately contain an escaped quote
    (`\\"`) or an escaped backslash (`\\\\`) -- neither should be
    mistaken for the string's closing quote, and a `{`/`}` appearing
    later, outside any string, must still balance correctly against
    the object's real extent, not get confused by what came before."""
    text = (
        r'{"thought": "she said \"hi\" and left \\ then", "action": "done"}'
        r"   trailing junk { not balanced"
    )

    objects = _find_balanced_json_objects(text)

    assert len(objects) == 1
    assert objects[0] == r'{"thought": "she said \"hi\" and left \\ then", "action": "done"}'
