"""The strict, provider-agnostic contract for one discovery turn.

The discovery loop (`cua.agent.discover`) asks the model for exactly
one JSON object describing what to do next, given the goal and the
current `Observation`. `AgentDecision` is that object's schema --
deliberately mirroring `cua.artifact.models.Step`'s own per-action
shape rules (a targeted action needs a target; `navigate` needs a
destination, not a target; `extract` needs an `output_field`; etc.) so
a decision that survives validation here already looks like a Step.
Two action values have no `cua.artifact.models.ActionType` counterpart:
`done` (the goal is reached -- end the run successfully) and `stuck`
(no safe way to proceed -- escalate).

`parse_agent_decision` never guesses. A response that isn't exactly one
well-formed decision -- unparsable JSON, an extra/missing field, an
inconsistent field for the given action -- raises `AgentDecisionError`
rather than being coerced into "probably meant this," the same
philosophy `cua.locator.resolve_target` applies to an ambiguous match.
`cua.agent.discover` is what turns that exception into a clean `STUCK`
outcome; this module only ever validates or refuses.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

_TARGETED_ACTIONS = frozenset({"click", "wait_for", "assert_checkpoint", "dismiss", "type", "select", "extract"})
_VALUE_ACTIONS = frozenset({"type", "select"})
_TERMINAL_ACTIONS = frozenset({"done", "stuck"})

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class AgentDecisionError(ValueError):
    """The model's raw response could not be parsed into exactly one
    valid `AgentDecision`."""


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thought: str
    action: Literal[
        "navigate", "click", "type", "select", "wait_for", "extract", "assert_checkpoint", "dismiss", "done", "stuck"
    ]
    frame: str | None = None
    ref: str | None = None
    value: str | None = None
    output_field: str | None = None
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _null_reason_means_omitted(cls, data: object) -> object:
        """Some real models (observed live: Bedrock Claude Haiku 4.5)
        send an explicit `"reason": null` rather than omitting the
        field on a non-terminal action -- both mean "no reason given,"
        so treat them identically instead of failing validation on a
        `str`-typed field that happens to have received `None`. `stuck`
        still requires a real, non-blank reason either way (enforced
        below, same as the already-omitted/blank cases)."""
        if isinstance(data, dict) and data.get("reason") is None and "reason" in data:
            data = {**data, "reason": ""}
        return data

    @model_validator(mode="after")
    def _validate_shape(self) -> AgentDecision:
        action = self.action

        if action == "navigate":
            if self.value is None:
                raise ValueError("'navigate' decision requires 'value' (the destination)")
            if self.frame is not None or self.ref is not None:
                raise ValueError("'navigate' decision must not set 'frame'/'ref' -- it has no target")
            if self.output_field is not None:
                raise ValueError("'navigate' decision must not set 'output_field'")

        elif action in _TARGETED_ACTIONS:
            if self.frame is None or self.ref is None:
                raise ValueError(f"'{action}' decision requires 'frame' and 'ref'")
            wants_value = action in _VALUE_ACTIONS
            if wants_value and self.value is None:
                raise ValueError(f"'{action}' decision requires 'value'")
            if not wants_value and self.value is not None:
                raise ValueError(f"'{action}' decision must not set 'value'")
            wants_output = action == "extract"
            if wants_output and self.output_field is None:
                raise ValueError("'extract' decision requires 'output_field'")
            if not wants_output and self.output_field is not None:
                raise ValueError(f"'{action}' decision must not set 'output_field'")

        else:  # action in _TERMINAL_ACTIONS
            if self.frame is not None or self.ref is not None or self.value is not None or self.output_field is not None:
                raise ValueError(f"'{action}' decision must not set 'frame'/'ref'/'value'/'output_field'")
            if action == "stuck" and not self.reason.strip():
                raise ValueError("'stuck' decision requires a non-empty 'reason'")

        return self


def parse_agent_decision(raw: str) -> AgentDecision:
    for candidate in _candidate_json_strings(raw):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        try:
            return AgentDecision.model_validate(data)
        except ValidationError:
            continue
    raise AgentDecisionError(f"could not parse a valid decision from the model's response: {raw!r}")


def _candidate_json_strings(raw: str) -> list[str]:
    """Every substring worth trying as the decision JSON, in order of
    how likely each is to be the real one: the whole trimmed response
    first (the common case -- the model followed instructions exactly),
    then a fenced code block if present, then every balanced `{...}`
    object found anywhere in the text (in document order) as a last
    resort against a chatty model that added prose around the JSON, or
    even a second, unrelated-looking object earlier in the response."""
    candidates = [raw.strip()]
    fence_match = _FENCE_RE.search(raw)
    if fence_match:
        candidates.append(fence_match.group(1).strip())
    candidates.extend(_find_balanced_json_objects(raw))
    return candidates


def _find_balanced_json_objects(text: str) -> list[str]:
    objects: list[str] = []
    depth = 0
    start: int | None = None
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start : i + 1])
                start = None

    return objects
