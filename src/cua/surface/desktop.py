"""Desktop surface seam -- design, not implementation (assignment 3.7).

A real implementation would perceive via the platform's native
accessibility API instead of ARIA/DOM:

  - Windows: UI Automation (role, Name, ControlType, AutomationId when
    present)
  - macOS: the Accessibility API (AXRole, AXTitle, AXValue)
  - a JVM desktop app: the Java Access Bridge

Each maps onto exactly the same `ObservedNode(role, name, attrs, ...)`
shape `WebSurface` produces from ARIA -- an accessibility tree is an
OS-level concept, not a web one, which is precisely why this seam is a
single shared interface rather than a parallel one. Acting means
invoking that platform API's equivalent of click/type/select on the
element a `(frame, ref)` names; "frame" would generalize to a window or
pane identifier instead of an iframe name.

This class intentionally raises rather than half-implementing something
misleading: nothing here has been exercised against a real desktop app,
and the assignment does not ask for that -- it asks for a design that
doesn't paint the system into a corner, which is what conforming to
`Surface` demonstrates. Swap this in wherever a `WebSurface` is used
today and nothing above this layer (locator resolution, replay, the
agent loop) would need to change.
"""
from __future__ import annotations

from cua.surface.base import Surface
from cua.surface.models import ActionResult, Observation, SurfaceAction

_NOT_IMPLEMENTED = (
    "DesktopSurface is a design seam, not an implementation -- see "
    "REPORT.md Section 4 (Heterogeneity & multi-tenant). A real build "
    "would wrap Windows UIA / macOS Accessibility / the Java Access "
    "Bridge behind this same Surface interface."
)


class DesktopSurface(Surface):
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def observe(self) -> Observation:  # pragma: no cover - unreachable seam
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def act(self, action: SurfaceAction) -> ActionResult:  # pragma: no cover
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def screenshot(self) -> bytes:  # pragma: no cover - unreachable seam
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def current_url(self) -> str:  # pragma: no cover - unreachable seam
        raise NotImplementedError(_NOT_IMPLEMENTED)
