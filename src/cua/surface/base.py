"""The Surface interface: perceive/act, independent of what's underneath.

Deliberately excludes anything resembling `open()`/`close()`: the live
session must be able to survive a human-escalation handoff (assignment
3.6 -- "let them take control of the live session... then hand control
back"), so session lifecycle belongs to whatever creates a Surface (the
agent loop, the replay engine), never to the Surface itself. A Surface is
a thin adapter over an already-live session, nothing more.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from cua.surface.models import ActionResult, Observation, SurfaceAction


class Surface(ABC):
    @abstractmethod
    def observe(self) -> Observation:
        """Perceive everything currently on screen, across every
        frame/region the surface exposes."""

    @abstractmethod
    def act(self, action: SurfaceAction) -> ActionResult:
        """Perform one action against a `(frame, ref)` from the most
        recent `observe()` (or none, for NAVIGATE). Never raises for an
        expected failure (missing element, timeout) -- returns a
        structured failure instead."""

    @abstractmethod
    def screenshot(self) -> bytes:
        """A raw image of the current state, for evidence and for the
        LLM's reasoning during discovery."""

    @abstractmethod
    def current_url(self) -> str:
        """Best-effort location indicator. On a frame-heavy legacy
        surface this may barely change while the real state moves inside
        a content frame -- callers should prefer observed content over
        the URL for checkpoints."""
