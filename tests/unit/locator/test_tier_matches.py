"""tier_matches() is the small public seam Phase 5's known-outcome
detection needs: 'is this single marker tier present anywhere', with none
of resolve_target()'s fallback-ladder or ambiguity-policy machinery."""
import pytest

from cua.artifact.models import LocatorStrategy, LocatorTier
from cua.locator import tier_matches

pytestmark = pytest.mark.unit


def _role(role, name):
    return LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": role, "name": name})


def test_returns_every_matching_node_not_just_a_unique_one(search_page_observation):
    obs = search_page_observation
    from tests.unit.locator.conftest import node

    obs.nodes.append(node("e99", "contentFrame", "button", "Search", parent_ref="e12", depth=6))
    matches = tier_matches(obs, _role("button", "Search"))
    assert {n.ref for n in matches} == {"e13", "e99"}


def test_no_match_is_an_empty_list(search_page_observation):
    matches = tier_matches(search_page_observation, _role("heading", "Does Not Exist"))
    assert matches == []


def test_single_match(search_page_observation):
    matches = tier_matches(search_page_observation, _role("button", "Search"))
    assert [n.ref for n in matches] == ["e13"]
