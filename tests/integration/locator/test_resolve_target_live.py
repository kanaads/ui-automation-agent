"""End-to-end proof that the pipeline Phase 1 -> Phase 3 -> Phase 4 fits
together: the *actual* Targets from the artifact fixture used to design
and test the schema (tests/unit/artifact/conftest.py) resolve correctly
against a live Observation captured from a real browser session on the
real target app -- not just against hand-written synthetic nodes.
"""
import pytest

from cua.artifact.models import LocatorStrategy, LocatorTier, Target
from cua.locator.resolve import ResolutionStatus, resolve_target
from cua.surface.web import WebSurface

pytestmark = pytest.mark.integration


def _role_locator(role: str, name: str) -> LocatorTier:
    return LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": role, "name": name})


def _label_locator(near_text: str, control_type: str) -> LocatorTier:
    return LocatorTier(
        strategy=LocatorStrategy.LABEL_PROXIMITY, params={"near_text": near_text, "control_type": control_type}
    )


def test_search_button_target_resolves_at_tier_zero_live(live_app, page):
    page.goto(f"{live_app}/content/search")
    surface = WebSurface(page)
    obs = surface.observe()

    target = Target(primary=_role_locator("button", "Search"), fallbacks=[_label_locator("Member Number", "button")])
    res = resolve_target(obs, target)

    assert res.status == ResolutionStatus.RESOLVED
    assert res.tier_index == 0
    assert res.strategy == LocatorStrategy.ROLE_NAME


def test_member_id_field_target_falls_back_to_label_proximity_live(live_app, page):
    """The exact scenario the schema was designed around: the search
    field's role+name tier fails for real (no accessible name), and the
    label-proximity fallback is what actually resolves it -- proven
    against the live app, not asserted in a docstring."""
    page.goto(f"{live_app}/content/search")
    surface = WebSurface(page)
    obs = surface.observe()

    target = Target(
        primary=_role_locator("textbox", "Member Number"),
        fallbacks=[_label_locator("Member Number", "textbox")],
    )
    res = resolve_target(obs, target)

    assert res.status == ResolutionStatus.RESOLVED
    assert res.tier_index == 1
    assert res.strategy == LocatorStrategy.LABEL_PROXIMITY
    # navigating straight to the fragment route (rather than through the
    # /app shell's named iframe) makes it the top-level document itself.
    assert res.frame == "main"


def test_savings_balance_target_resolves_and_the_ref_is_extractable(live_app, page):
    page.goto(f"{live_app}/content/detail?id=10001")
    surface = WebSurface(page)
    obs = surface.observe()

    target = Target(
        primary=_role_locator("cell", "Savings Balance"),
        fallbacks=[_label_locator("Savings Balance", "cell")],
    )
    res = resolve_target(obs, target)
    assert res.status == ResolutionStatus.RESOLVED

    from cua.artifact.models import ActionType
    from cua.surface.models import SurfaceAction

    result = surface.act(SurfaceAction(action=ActionType.EXTRACT, frame=res.frame, ref=res.ref))
    assert result.ok
    assert result.extracted_value == "$4,231.50"


def test_tenant_b_relabeled_button_breaks_the_base_role_name_tier_live(live_app, live_tenant_b_app, page):
    """The cross-tenant drift story, proven live: the SAME Target
    recorded against the base tenant's 'Search' button genuinely fails
    tier 1 on tenant_b (labeled 'Find Member'), and only a fallback
    that doesn't depend on the button's exact text -- anchored_region --
    still resolves it. This is the concrete evidence behind the
    heterogeneity/multi-tenant design in REPORT.md."""
    page.goto(f"{live_tenant_b_app}/content/search")
    surface = WebSurface(page)
    obs = surface.observe()

    base_recorded_target = Target(primary=_role_locator("button", "Search"))
    res = resolve_target(obs, base_recorded_target)
    assert res.status == ResolutionStatus.NOT_FOUND  # genuinely broken by rebranding, not simulated

    # Only one button on the page, whatever its label -- "the 1st button in
    # this frame" survives the rename and resolves straight to the leaf
    # control itself (directly clickable), not to a row/cell wrapper.
    region_tier = LocatorTier(
        strategy=LocatorStrategy.ANCHORED_REGION, params={"frame": "main", "region": "button", "index": 0}
    )
    resilient_target = Target(primary=_role_locator("button", "Search"), fallbacks=[region_tier])
    res2 = resolve_target(obs, resilient_target)
    assert res2.status == ResolutionStatus.RESOLVED
    assert res2.tier_index == 1

    from cua.artifact.models import ActionType
    from cua.surface.models import SurfaceAction

    result = surface.act(SurfaceAction(action=ActionType.CLICK, frame=res2.frame, ref=res2.ref))
    assert result.ok  # proves the resolved ref is the button itself, not a wrapper
