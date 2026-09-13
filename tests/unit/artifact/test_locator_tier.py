"""LocatorTier is the schema's answer to 'how is each control identified'.

Each strategy has different required parameters. We validate those
per-strategy rather than accepting a free-form dict, because a malformed
locator that silently fails at replay time (rather than at authoring/review
time) is exactly the kind of bug this schema exists to prevent.
"""
import pytest
from pydantic import ValidationError

from cua.artifact.models import LocatorStrategy, LocatorTier, Target

pytestmark = pytest.mark.unit


def test_role_name_strategy_requires_role_and_name():
    with pytest.raises(ValidationError):
        LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "button"})


def test_role_name_strategy_valid():
    t = LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "button", "name": "Search"})
    assert t.params["name"] == "Search"


def test_label_proximity_requires_near_text_and_control_type():
    with pytest.raises(ValidationError):
        LocatorTier(strategy=LocatorStrategy.LABEL_PROXIMITY, params={"control_type": "button"})
    with pytest.raises(ValidationError):
        LocatorTier(strategy=LocatorStrategy.LABEL_PROXIMITY, params={"near_text": "Member Number"})


def test_label_proximity_valid():
    t = LocatorTier(
        strategy=LocatorStrategy.LABEL_PROXIMITY,
        params={"near_text": "Member Number", "control_type": "textbox"},
    )
    assert t.params["near_text"] == "Member Number"


def test_anchored_region_requires_frame_region_and_index():
    with pytest.raises(ValidationError):
        LocatorTier(strategy=LocatorStrategy.ANCHORED_REGION, params={"frame": "content"})


def test_anchored_region_valid():
    t = LocatorTier(
        strategy=LocatorStrategy.ANCHORED_REGION,
        params={"frame": "content", "region": "search_panel", "index": 0},
    )
    assert t.params["index"] == 0


def test_visual_template_stub_requires_asset_ref_and_confidence_min():
    """Tier 4 is intentionally stubbed (not executed by the replay engine in
    this system), but the schema still enforces its shape so the seam is
    real rather than a bare TODO string."""
    with pytest.raises(ValidationError):
        LocatorTier(strategy=LocatorStrategy.VISUAL_TEMPLATE, params={})


def test_visual_template_stub_valid_shape():
    t = LocatorTier(
        strategy=LocatorStrategy.VISUAL_TEMPLATE,
        params={"asset": "evidence/tpl_search_btn.png", "confidence_min": 0.9},
    )
    assert t.params["confidence_min"] == 0.9


def test_unknown_strategy_params_are_rejected():
    with pytest.raises(ValidationError):
        LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "button", "name": "x", "bogus": 1})


class TestTarget:
    def test_requires_primary(self):
        with pytest.raises(ValidationError):
            Target(fallbacks=[])

    def test_valid_with_primary_only(self):
        t = Target(primary=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "button", "name": "Search"}))
        assert t.fallbacks == []

    def test_default_ambiguity_policy_is_escalate(self):
        t = Target(primary=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "button", "name": "Search"}))
        assert t.ambiguity_policy == "escalate_on_ambiguous"

    def test_fallbacks_preserve_order(self):
        f1 = LocatorTier(strategy=LocatorStrategy.LABEL_PROXIMITY, params={"near_text": "x", "control_type": "button"})
        f2 = LocatorTier(strategy=LocatorStrategy.ANCHORED_REGION, params={"frame": "content", "region": "r", "index": 0})
        t = Target(
            primary=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "button", "name": "Search"}),
            fallbacks=[f1, f2],
        )
        assert t.fallbacks[0].strategy == LocatorStrategy.LABEL_PROXIMITY
        assert t.fallbacks[1].strategy == LocatorStrategy.ANCHORED_REGION
