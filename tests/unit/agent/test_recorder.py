"""cua.agent.recorder: infer_target() (turning one acted (frame, ref)
from one observation into a resilient, tiered Target) and
build_artifact_from_discovery() (turning a whole successful transcript
into a reviewable CapabilityArtifact). Fixtures mirror the real target
app's actual table-row shape (label cell, control cell, row siblings --
tests/unit/replay/test_engine.py's own _SEARCH_NODES), not an idealized
label-next-to-input DOM.
"""

import pytest

from cua.agent.contract import DiscoveryResult, DiscoveryStatus, DiscoveryStep
from cua.agent.decide import AgentDecision
from cua.agent.recorder import build_artifact_from_discovery, infer_target
from cua.artifact.models import ActionType, Checkpoint, LocatorStrategy, TenantScope
from cua.surface.models import ActionResult, Observation
from tests.unit.replay.conftest import node, role_tier

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# infer_target
# ---------------------------------------------------------------------------

_ROW_SHAPED_NODES = [
    node("e1", "contentFrame", "document"),
    node("e5", "contentFrame", "table", parent_ref="e1", depth=1),
    node("e6", "contentFrame", "rowgroup", parent_ref="e5", depth=2),
    node("e7", "contentFrame", "row", parent_ref="e6", depth=3),
    node("e8", "contentFrame", "cell", "Member Number:", parent_ref="e7", depth=4),
    node("e9", "contentFrame", "cell", parent_ref="e7", depth=4),
    node("e10", "contentFrame", "textbox", None, parent_ref="e9", depth=5),
    node("e11", "contentFrame", "row", parent_ref="e6", depth=3),
    node("e12", "contentFrame", "cell", parent_ref="e11", depth=4),
    node("e13", "contentFrame", "button", "Search", parent_ref="e12", depth=4),
]


def _row_shaped_observation() -> Observation:
    return Observation(nodes=list(_ROW_SHAPED_NODES), url="http://x/content/search", title="Member Search")


def test_a_named_node_gets_a_role_name_target():
    target = infer_target(_row_shaped_observation(), "contentFrame", "e13")

    assert target.primary.strategy == LocatorStrategy.ROLE_NAME
    assert target.primary.params == {"role": "button", "name": "Search"}
    assert target.fallbacks == []


def test_a_nameless_node_with_a_row_sibling_label_gets_a_label_proximity_target():
    target = infer_target(_row_shaped_observation(), "contentFrame", "e10")

    assert target.primary.strategy == LocatorStrategy.LABEL_PROXIMITY
    assert target.primary.params == {"near_text": "Member Number", "control_type": "textbox"}


def test_the_labels_trailing_colon_is_stripped():
    target = infer_target(_row_shaped_observation(), "contentFrame", "e10")

    assert target.primary.params["near_text"] == "Member Number"


def test_a_nameless_node_with_no_discoverable_label_falls_back_to_anchored_region():
    nodes = [
        node("t1", "main", "textbox", None),
        node("t2", "main", "textbox", None),
        node("t3", "main", "textbox", None),
    ]
    observation = Observation(nodes=nodes, url="http://x", title="?")

    target = infer_target(observation, "main", "t2")

    assert target.primary.strategy == LocatorStrategy.ANCHORED_REGION
    assert target.primary.params == {"frame": "main", "region": "textbox", "index": 1}


def test_a_dangling_parent_ref_stops_the_label_search_and_falls_back_to_anchored_region():
    """A node whose parent_ref points nowhere real (shouldn't happen in
    a genuine snapshot, but the search must not crash on it) simply
    ends the walk up early -- same "skipped, not crashed" treatment
    cua.locator.resolve_target already gives a dangling parent_ref."""
    nodes = [
        node("t1", "main", "textbox", None, parent_ref="missing-parent"),
    ]
    observation = Observation(nodes=nodes, url="http://x", title="?")

    target = infer_target(observation, "main", "t1")

    assert target.primary.strategy == LocatorStrategy.ANCHORED_REGION
    assert target.primary.params == {"frame": "main", "region": "textbox", "index": 0}


def test_a_nonexistent_ref_raises():
    with pytest.raises(ValueError, match="no node"):
        infer_target(_row_shaped_observation(), "contentFrame", "does-not-exist")


# `treat_name_as_data`: an EXTRACT target's own accessible name is often
# the very value being captured (a balance cell literally named
# "$4,231.50"), which would only ever match this one run again if used
# as a ROLE_NAME locator. This is the row shape a value cell actually
# has in the real target app (detail_content.html): label cell and
# value cell as DIRECT row siblings -- not nested one level deeper the
# way a labeled <input> control is.
_VALUE_CELL_NODES = [
    node("d1", "contentFrame", "document"),
    node("d5", "contentFrame", "row", parent_ref="d1", depth=1),
    node("d6", "contentFrame", "cell", "Savings Balance:", parent_ref="d5", depth=2),
    node("d7", "contentFrame", "cell", "$4,231.50", parent_ref="d5", depth=2),
]


def test_treat_name_as_data_skips_the_named_node_and_infers_its_row_sibling_label():
    observation = Observation(nodes=list(_VALUE_CELL_NODES), url="http://x/content/detail", title="Member Detail")

    target = infer_target(observation, "contentFrame", "d7", treat_name_as_data=True)

    assert target.primary.strategy == LocatorStrategy.LABEL_PROXIMITY
    assert target.primary.params == {"near_text": "Savings Balance", "control_type": "cell"}


def test_without_treat_name_as_data_the_same_value_cell_would_be_targeted_by_its_own_text():
    """Proves the flag is what changes the outcome -- without it,
    infer_target does exactly what it does for any other named node
    (correct there, wrong here, which is the whole point of the flag)."""
    observation = Observation(nodes=list(_VALUE_CELL_NODES), url="http://x/content/detail", title="Member Detail")

    target = infer_target(observation, "contentFrame", "d7", treat_name_as_data=False)

    assert target.primary.strategy == LocatorStrategy.ROLE_NAME
    assert target.primary.params == {"role": "cell", "name": "$4,231.50"}


# ---------------------------------------------------------------------------
# build_artifact_from_discovery
# ---------------------------------------------------------------------------


def _successful_result() -> DiscoveryResult:
    search_obs = _row_shaped_observation()
    final_obs = Observation(
        nodes=[node("d2", "contentFrame", "heading", "Member Detail")], url="http://y/content/detail", title="Member Detail"
    )
    return DiscoveryResult(
        status=DiscoveryStatus.GOAL_REACHED,
        goal="look up member 10001",
        reason="member detail is now showing",
        final_observation=final_obs,
        transcript=[
            DiscoveryStep(
                decision=AgentDecision(thought="go to search", action="navigate", value="/app?start=/content/search"),
                observation=search_obs,
                action_result=ActionResult(ok=True),
            ),
            DiscoveryStep(
                decision=AgentDecision(thought="type the id", action="type", frame="contentFrame", ref="e10", value="10001"),
                observation=search_obs,
                action_result=ActionResult(ok=True),
            ),
            DiscoveryStep(
                decision=AgentDecision(thought="click search", action="click", frame="contentFrame", ref="e13"),
                observation=search_obs,
                action_result=ActionResult(ok=True),
            ),
        ],
    )


def _checkpoint() -> Checkpoint:
    return Checkpoint(description="Member detail page is showing", detection=role_tier("heading", "Member Detail"))


def test_builds_one_step_per_transcript_entry_in_order():
    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="get_member_detail",
        version="1.0.0",
        description="Look up a member and view their detail page.",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
    )

    assert [s.action for s in artifact.steps] == [ActionType.NAVIGATE, ActionType.TYPE, ActionType.CLICK]
    assert [s.step_id for s in artifact.steps] == ["step_1", "step_2", "step_3"]


def test_navigate_step_gets_its_literal_destination():
    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
    )

    assert artifact.steps[0].literal_value == "/app?start=/content/search"
    assert artifact.steps[0].input_param is None


def test_type_step_gets_an_inferred_target_and_its_literal_value():
    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
    )

    type_step = artifact.steps[1]
    assert type_step.literal_value == "10001"
    assert type_step.target.primary.strategy == LocatorStrategy.LABEL_PROXIMITY
    assert type_step.target.primary.params["near_text"] == "Member Number"


def test_policy_scope_derives_allowed_action_types_from_what_was_actually_used():
    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
    )

    assert set(artifact.policy_scope.allowed_action_types) == {ActionType.NAVIGATE, ActionType.TYPE, ActionType.CLICK}


def test_policy_scope_derives_allowed_domains_from_every_observed_url_including_the_final_one():
    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
    )

    # "x" from every transcript step's observation, "y" only from
    # final_observation -- proving it's genuinely included, not just
    # coincidentally the same domain as everything else.
    assert artifact.policy_scope.allowed_domains == ["x", "y"]


def test_default_provenance_is_llm_discovery():
    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
    )

    assert artifact.provenance.kind == "llm_discovery"


def test_every_recorded_step_defaults_to_safe_risk():
    """Recording never guesses at risk classification -- see module
    docstring. A human reviewer must explicitly upgrade a step before
    it can do anything cua.policy would otherwise block by default."""
    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
    )

    from cua.artifact.models import RiskLevel

    assert all(s.risk == RiskLevel.SAFE for s in artifact.steps)


def test_parameterize_swaps_a_literal_value_for_an_input_param_and_declares_it():
    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
        parameterize={"10001": "member_id"},
    )

    type_step = artifact.steps[1]
    assert type_step.input_param == "member_id"
    assert type_step.literal_value is None
    assert [p.name for p in artifact.input_schema] == ["member_id"]
    assert artifact.input_schema[0].type.value == "string"


def test_parameterize_does_not_redeclare_an_already_supplied_param_spec():
    from cua.artifact.models import ParamSpec, ParamType

    artifact = build_artifact_from_discovery(
        _successful_result(),
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
        input_schema=[ParamSpec(name="member_id", type=ParamType.STRING, required=True, description="a caller-authored spec")],
        parameterize={"10001": "member_id"},
    )

    assert len(artifact.input_schema) == 1
    assert artifact.input_schema[0].description == "a caller-authored spec"


def test_refuses_to_record_a_run_that_did_not_reach_its_goal():
    stuck_result = DiscoveryResult(status=DiscoveryStatus.STUCK, goal="g", reason="no way forward")

    with pytest.raises(ValueError, match="did not reach its goal"):
        build_artifact_from_discovery(
            stuck_result,
            capability_id="c",
            version="1.0.0",
            description="d",
            tenant_scope=TenantScope(vendor_app_id="meridian_core"),
            checkpoint=_checkpoint(),
        )


def test_a_zero_step_transcript_is_refused_by_the_artifact_schema_itself():
    empty_result = DiscoveryResult(status=DiscoveryStatus.GOAL_REACHED, goal="g", reason="already there")

    with pytest.raises(Exception):  # noqa: B017 -- pydantic's own ValidationError, exercised as a black box here
        build_artifact_from_discovery(
            empty_result,
            capability_id="c",
            version="1.0.0",
            description="d",
            tenant_scope=TenantScope(vendor_app_id="meridian_core"),
            checkpoint=_checkpoint(),
        )


def test_extract_step_carries_its_output_field_and_infers_a_label_target_not_its_own_value():
    """A caller-supplied output_schema is the recorder's own job to
    wire up (output_field); a matching ParamSpec entry is left to the
    caller, same as any other output_schema (see module docstring)."""
    from cua.artifact.models import OutputSpec, ParamType

    result = DiscoveryResult(
        status=DiscoveryStatus.GOAL_REACHED,
        goal="read the balance",
        reason="balance captured",
        transcript=[
            DiscoveryStep(
                decision=AgentDecision(
                    thought="extract it", action="extract", frame="contentFrame", ref="d7", output_field="balance_text"
                ),
                observation=Observation(nodes=list(_VALUE_CELL_NODES), url="http://x/content/detail", title="Member Detail"),
                action_result=ActionResult(ok=True, extracted_value="$4,231.50"),
            )
        ],
    )

    artifact = build_artifact_from_discovery(
        result,
        capability_id="c",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=_checkpoint(),
        output_schema=[OutputSpec(name="balance_text", type=ParamType.STRING)],
    )

    assert artifact.steps[0].output_field == "balance_text"
    assert artifact.steps[0].target.primary.strategy == LocatorStrategy.LABEL_PROXIMITY
    assert artifact.steps[0].target.primary.params == {"near_text": "Savings Balance", "control_type": "cell"}
