"""Renders one discovery turn into the message list `LLMClient.complete`
takes: a fixed system prompt describing the JSON decision contract
(`cua.agent.decide.AgentDecision`), plus a user turn with the goal, a
plain-text rendering of the current `Observation` (every perceivable
node's frame/ref/role/name -- the same primitives `cua.locator` matches
against, so an artifact recorded from this transcript is targeting
exactly what the model saw), and a short history of what's been tried
so far.
"""
from __future__ import annotations

from collections.abc import Sequence

from cua.agent.contract import DiscoveryStep
from cua.agent.llm.base import LLMMessage
from cua.surface.models import Observation

_SYSTEM_PROMPT = """\
You are an automation agent. You are given a GOAL and a live perception \
of a web page (every element's frame, ref, role, and accessible name). \
Decide the single next action that moves toward the goal.

Respond with EXACTLY one JSON object and nothing else: no markdown code \
fences, no commentary before or after it. The object has these fields:

  thought       (string, always) brief reasoning for this step
  action        (string, always) one of: navigate, click, type, select,
                wait_for, extract, assert_checkpoint, dismiss, done, stuck
  frame, ref    (for click/type/select/wait_for/extract/assert_checkpoint
                /dismiss) copied EXACTLY from the perception below --
                never invent or guess one
  value         (for navigate: the destination path; for type/select:
                the value to enter)
  output_field  (for extract only) a short snake_case name for the
                captured value
  reason        (for stuck only) why nothing on screen lets you proceed

Rules:
- Use "done" once the current perception shows the goal has already
  been accomplished.
- Use "stuck" if no visible element lets you make progress. Never
  guess at a frame/ref that isn't listed below, and never invent a
  role or name that doesn't appear in the perception.
- One action per response. Wait for the next perception before deciding
  the next step -- the page may have changed.\
"""


def build_messages(*, goal: str, observation: Observation, history: Sequence[DiscoveryStep]) -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content=_SYSTEM_PROMPT),
        LLMMessage(role="user", content=_render_turn(goal, observation, history)),
    ]


def _render_turn(goal: str, observation: Observation, history: Sequence[DiscoveryStep]) -> str:
    lines = [f"GOAL: {goal}", ""]

    if history:
        lines.append("STEPS TAKEN SO FAR:")
        for i, step in enumerate(history, start=1):
            d = step.decision
            outcome = "ok" if step.action_result.ok else f"FAILED: {step.action_result.error}"
            lines.append(f"  {i}. {d.action} frame={d.frame!r} ref={d.ref!r} value={d.value!r} -> {outcome}")
        lines.append("")

    lines.append(f"CURRENT PERCEPTION (url={observation.url!r} title={observation.title!r}):")
    for node in observation.nodes:
        lines.append(f"  frame={node.frame!r} ref={node.ref!r} role={node.role!r} name={node.name!r}")

    return "\n".join(lines)
