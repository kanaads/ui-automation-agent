"""The perception/action vocabulary a `Surface` speaks.

This is the seam the assignment (3.7) asks about: `ObservedNode` and
`Observation` are how any surface -- web, legacy web, a native desktop
app tomorrow -- represents "what's currently on screen" in one shared
shape (role, accessible name, a stable-within-this-observation `ref`,
which named frame/region it lives in). `SurfaceAction` is how any surface
is told to act, always against a `(frame, ref)` a prior `observe()`
handed back -- never against a raw coordinate. The locator layer
(`cua.locator`) resolves an artifact's tiered `Target` down to a concrete
`(frame, ref)` by searching an `Observation`; this module has no
knowledge of artifacts or locator tiers, only of the runtime handshake
between perceiving a surface and acting on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cua.artifact.models import ActionType


@dataclass(frozen=True)
class ObservedNode:
    """One perceivable element, as reported by a single `observe()` call.

    `ref` is opaque and only meaningful for the frame/observation it came
    from -- two different frames can legitimately reuse the same raw ref,
    so every lookup is keyed by `(frame, ref)`, never `ref` alone.
    """

    ref: str | None
    frame: str
    role: str
    name: str | None
    attrs: dict[str, object] = field(default_factory=dict)
    depth: int = 0
    parent_ref: str | None = None


@dataclass
class Observation:
    """A snapshot of everything currently perceivable across every frame
    of a surface, plus enough page-level context (url/title) for logging
    and evidence. Deliberately dumb: no resolution logic beyond exact
    lookups and simple substring search -- the tiered fallback strategy
    lives one layer up, in `cua.locator`, which searches an Observation
    rather than being part of it.
    """

    nodes: list[ObservedNode]
    url: str
    title: str

    def find_by_ref(self, frame: str, ref: str) -> ObservedNode | None:
        for n in self.nodes:
            if n.frame == frame and n.ref == ref:
                return n
        return None

    def by_role_name(self, role: str, name: str, *, frame: str | None = None) -> list[ObservedNode]:
        return [
            n
            for n in self.nodes
            if n.role == role and n.name == name and (frame is None or n.frame == frame)
        ]

    def by_text_near(self, substring: str, *, frame: str | None = None) -> list[ObservedNode]:
        """Nodes whose accessible name contains `substring` -- the raw
        material the LABEL_PROXIMITY locator tier searches over."""
        return [
            n
            for n in self.nodes
            if n.name and substring in n.name and (frame is None or n.frame == frame)
        ]


@dataclass
class SurfaceAction:
    """One low-level instruction to a Surface: act on a specific
    `(frame, ref)` from a prior observation (or none, for NAVIGATE)."""

    action: ActionType
    frame: str | None = None
    ref: str | None = None
    value: str | None = None
    timeout_ms: int = 5000


@dataclass
class ActionResult:
    """What a Surface hands back after `act()`. Never raises for an
    expected failure mode (element gone, timeout) -- callers get a
    structured result and decide what it means (business outcome,
    recoverable, hard failure) one layer up, in `cua.replay`."""

    ok: bool
    error: str | None = None
    extracted_value: str | None = None
