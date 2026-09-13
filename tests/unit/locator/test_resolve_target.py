"""resolve_target() is where the artifact's tiered Target (Phase 1) meets
a live Observation (Phase 3). This is the load-bearing piece of the
'locator/control-robustness strategy' the assignment weighs heavily:
getting the fallback-ladder and ambiguity semantics right here is what
makes the whole schema's tier design more than decoration.
"""
import pytest

from cua.artifact.models import LocatorStrategy, LocatorTier, Target
from cua.locator.resolve import ResolutionStatus, resolve_target
from tests.unit.locator.conftest import node

pytestmark = pytest.mark.unit


def role_tier(role, name):
    return LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": role, "name": name})


def label_tier(near_text, control_type):
    return LocatorTier(strategy=LocatorStrategy.LABEL_PROXIMITY, params={"near_text": near_text, "control_type": control_type})


def region_tier(frame, region, index):
    return LocatorTier(strategy=LocatorStrategy.ANCHORED_REGION, params={"frame": frame, "region": region, "index": index})


def visual_tier():
    return LocatorTier(strategy=LocatorStrategy.VISUAL_TEMPLATE, params={"asset": "x.png", "confidence_min": 0.9})


class TestRoleNamePrimary:
    def test_resolves_uniquely_at_tier_zero(self, search_page_observation):
        target = Target(primary=role_tier("button", "Search"))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.RESOLVED
        assert res.tier_index == 0
        assert res.strategy == LocatorStrategy.ROLE_NAME
        assert res.frame == "contentFrame"
        assert res.ref == "e13"

    def test_no_match_falls_through_to_fallback(self, search_page_observation):
        """The textbox has no accessible name (deliberately hostile), so
        tier 1 finds nothing and resolution must fall to tier 2."""
        target = Target(
            primary=role_tier("textbox", "Member Number"),
            fallbacks=[label_tier("Member Number", "textbox")],
        )
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.RESOLVED
        assert res.tier_index == 1
        assert res.strategy == LocatorStrategy.LABEL_PROXIMITY
        assert res.ref == "e10"


class TestLabelProximity:
    def test_resolves_the_control_inside_the_labels_row(self, search_page_observation):
        target = Target(primary=label_tier("Member Number", "textbox"))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.RESOLVED
        assert res.ref == "e10"

    def test_resolves_a_non_interactive_cell_by_nearby_label(self, detail_page_observation):
        target = Target(primary=label_tier("Savings Balance", "cell"))
        res = resolve_target(detail_page_observation, target)
        assert res.status == ResolutionStatus.RESOLVED
        assert res.ref == "e11"

    def test_no_matching_label_text_is_not_found(self, search_page_observation):
        target = Target(primary=label_tier("Does Not Exist", "textbox"))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.NOT_FOUND

    def test_label_matches_but_no_control_of_that_type_nearby(self, search_page_observation):
        target = Target(primary=label_tier("Member Number", "checkbox"))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.NOT_FOUND

    def test_anchor_with_a_dangling_parent_ref_is_skipped_not_crashed(self, search_page_observation):
        """A malformed/partial observation shouldn't blow up resolution --
        an anchor whose parent_ref doesn't resolve to any real node (root
        node, or a snapshot capture gap) is just skipped, not raised."""
        obs = search_page_observation
        obs.nodes.append(
            node("e100", "contentFrame", "cell", "Member Number: stray", parent_ref="does_not_exist", depth=9)
        )
        target = Target(primary=label_tier("Member Number", "textbox"))
        res = resolve_target(obs, target)
        # the well-formed anchor (e8) still resolves the real textbox e10;
        # the dangling one (e100) contributes nothing and raises nothing.
        assert res.status == ResolutionStatus.RESOLVED
        assert res.ref == "e10"


class TestAnchoredRegion:
    def test_resolves_the_nth_node_of_that_role_directly(self, search_page_observation):
        # only one button in the frame -- index 0 resolves straight to it,
        # not to a row/cell wrapper around it.
        target = Target(primary=region_tier("contentFrame", "button", 0))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.RESOLVED
        assert res.ref == "e13"

    def test_resolves_by_ordinal_among_several_nodes_of_that_role(self, search_page_observation):
        # cells in document order: e8, e9, e12 -- index 2 is e12.
        target = Target(primary=region_tier("contentFrame", "cell", 2))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.RESOLVED
        assert res.ref == "e12"

    def test_out_of_range_index_is_not_found(self, search_page_observation):
        target = Target(primary=region_tier("contentFrame", "button", 99))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.NOT_FOUND

    def test_unknown_region_role_is_not_found(self, search_page_observation):
        target = Target(primary=region_tier("contentFrame", "not_a_real_role", 0))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.NOT_FOUND

    def test_wrong_frame_is_not_found(self, search_page_observation):
        target = Target(primary=region_tier("navFrame", "button", 0))
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.NOT_FOUND


class TestVisualTemplateStub:
    def test_visual_template_alone_is_not_found(self, search_page_observation):
        """Tier 4 is schema-validated but not executed by this replay
        engine (documented cut) -- it must never silently 'succeed'."""
        target = Target(primary=visual_tier())
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.NOT_FOUND

    def test_visual_template_as_a_fallback_is_never_reached_when_primary_resolves(self, search_page_observation):
        target = Target(primary=role_tier("button", "Search"), fallbacks=[visual_tier()])
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.RESOLVED
        assert res.tier_index == 0


class TestAmbiguity:
    def test_escalate_on_ambiguous_stops_at_the_first_ambiguous_tier(self, search_page_observation):
        obs = search_page_observation
        obs.nodes.append(node("e99", "contentFrame", "button", "Search", parent_ref="e12", depth=6))
        target = Target(primary=role_tier("button", "Search"), ambiguity_policy="escalate_on_ambiguous")
        res = resolve_target(obs, target)
        assert res.status == ResolutionStatus.AMBIGUOUS
        assert res.tier_index == 0
        assert len(res.candidates) == 2

    def test_escalate_on_ambiguous_never_tries_fallbacks(self, search_page_observation):
        obs = search_page_observation
        obs.nodes.append(node("e99", "contentFrame", "button", "Search", parent_ref="e12", depth=6))
        target = Target(
            primary=role_tier("button", "Search"),
            fallbacks=[label_tier("Member Number", "textbox")],  # would resolve uniquely if tried
            ambiguity_policy="escalate_on_ambiguous",
        )
        res = resolve_target(obs, target)
        assert res.status == ResolutionStatus.AMBIGUOUS
        assert res.tier_index == 0

    def test_first_unique_match_keeps_trying_fallbacks_after_an_ambiguous_tier(self, search_page_observation):
        obs = search_page_observation
        obs.nodes.append(node("e99", "contentFrame", "button", "Search", parent_ref="e12", depth=6))
        target = Target(
            primary=role_tier("button", "Search"),
            # the extra button makes ANCHORED_REGION on "button" ambiguous too,
            # but there's only one rowgroup in the frame -- unique at index 0.
            fallbacks=[region_tier("contentFrame", "rowgroup", 0)],
            ambiguity_policy="first_unique_match",
        )
        res = resolve_target(obs, target)
        assert res.status == ResolutionStatus.RESOLVED
        assert res.tier_index == 1
        assert res.ref == "e6"

    def test_first_unique_match_reports_ambiguous_only_after_exhausting_every_tier(self, search_page_observation):
        obs = search_page_observation
        obs.nodes.append(node("e99", "contentFrame", "button", "Search", parent_ref="e12", depth=6))
        target = Target(
            primary=role_tier("button", "Search"),
            fallbacks=[label_tier("Does Not Exist", "button")],  # not found, doesn't help
            ambiguity_policy="first_unique_match",
        )
        res = resolve_target(obs, target)
        assert res.status == ResolutionStatus.AMBIGUOUS
        assert res.tier_index == 0  # reports the first tier that was ambiguous


class TestNotFound:
    def test_every_tier_empty_is_not_found(self, search_page_observation):
        target = Target(
            primary=role_tier("button", "Nonexistent"),
            fallbacks=[label_tier("Nonexistent", "button")],
        )
        res = resolve_target(search_page_observation, target)
        assert res.status == ResolutionStatus.NOT_FOUND
        assert res.frame is None
        assert res.ref is None
