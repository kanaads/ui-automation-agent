"""Validates a caller's raw invocation dict against a CapabilityArtifact's
`input_schema` *before* any Surface is touched.

This is deliberately not folded into the engine's step loop: a bad
invocation (missing/extra/mistyped input, or an artifact whose steps
need a value nobody can ever supply) is the caller's bug, not something
that happened in the UI, so it raises `ReplayInputError` outright rather
than coming back as a `ReplayResult` the caller might mistake for "the
system got stuck."
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from cua.artifact.models import CapabilityArtifact, ParamSpec, ParamType

_TYPE_CHECKS: dict[ParamType, type | tuple[type, ...]] = {
    ParamType.STRING: str,
    ParamType.INTEGER: int,
    ParamType.NUMBER: (int, float),
    ParamType.BOOLEAN: bool,
}


class ReplayInputError(ValueError):
    """The caller's invocation doesn't satisfy the artifact's contract."""


def validate_inputs(artifact: CapabilityArtifact, raw_inputs: Mapping[str, Any]) -> dict[str, Any]:
    declared = {p.name: p for p in artifact.input_schema}

    unknown = sorted(set(raw_inputs) - set(declared))
    if unknown:
        raise ReplayInputError(f"unknown input(s): {unknown}")

    resolved: dict[str, Any] = {}
    for name, spec in declared.items():
        if name in raw_inputs:
            resolved[name] = _coerce_and_validate(spec, raw_inputs[name])
        elif spec.default is not None:
            resolved[name] = spec.default
        elif spec.required:
            raise ReplayInputError(f"missing required input '{name}'")
        # else: optional, no default, not supplied -> stays absent

    _ensure_step_dependencies_satisfied(artifact, resolved)
    return resolved


def _coerce_and_validate(spec: ParamSpec, value: Any) -> Any:
    if spec.type == ParamType.ENUM:
        if value not in (spec.enum_values or []):
            raise ReplayInputError(f"input '{spec.name}': '{value}' is not one of {spec.enum_values}")
        return value

    expected = _TYPE_CHECKS[spec.type]
    # bool is an int subclass in Python; never accept one where the other
    # is declared, or an int would silently pass a boolean-typed input.
    if isinstance(value, bool) != (spec.type == ParamType.BOOLEAN) or not isinstance(value, expected):
        raise ReplayInputError(f"input '{spec.name}': expected {spec.type.value}, got {type(value).__name__}")

    if spec.type == ParamType.STRING:
        assert isinstance(value, str)  # guaranteed by the isinstance check above; narrows for re.fullmatch
        if spec.pattern is not None and not re.fullmatch(spec.pattern, value):
            raise ReplayInputError(f"input '{spec.name}': '{value}' does not match pattern {spec.pattern!r}")

    return value


def _ensure_step_dependencies_satisfied(artifact: CapabilityArtifact, resolved: dict[str, Any]) -> None:
    for step in artifact.steps:
        if step.input_param is not None and step.input_param not in resolved:
            raise ReplayInputError(
                f"step '{step.step_id}' requires input '{step.input_param}', "
                "which was not supplied and has no default"
            )
