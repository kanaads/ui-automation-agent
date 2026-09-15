"""The Capability Artifact schema.

This is the contract described in the assignment (Section 3.2): a typed,
versioned, serializable description of a reusable flow, decoupled from the
raw discovery transcript. A calling AI agent invokes a capability by name
with typed parameters and gets typed outputs back; a human reviewer can
read the same document and understand what it does, needs, and returns.

Design summary (see /REPORT.md for the full rationale):

  CapabilityArtifact
  ├── input_schema / output_schema   -- the typed function signature
  ├── steps: [Step]                  -- the ordered, replayable flow
  │     └── target: Target           -- HOW a control is identified
  │           ├── primary            -- tier 1: role + accessible name
  │           └── fallbacks: [...]   -- tier 2/3, tried in order on miss
  │                                     (tier 4 "visual_template" is a
  │                                      validated shape, not executed --
  │                                      see cua.locator for the seam)
  ├── checkpoint                     -- how we know the goal was reached
  ├── known_outcomes                 -- business outcomes / recoverable /
  │                                     hard-failure signatures declared
  │                                     up front, not discovered ad hoc
  ├── policy_scope                   -- the artifact's own allowlist
  │                                     footprint (must cover what it does)
  ├── tenant_scope                   -- base capability vs. per-tenant
  │                                      override, for cross-tenant reuse
  └── content_hash                   -- SHA-256 seal over the canonical
                                         payload (everything except this
                                         field); verified on load

Every cross-reference (input_param -> input_schema, output_field ->
output_schema, action types -> policy_scope) is validated at construction
time. An artifact that fails to validate should never be saved, let alone
replayed. The content_hash seal answers "which exact version of this
capability ran?" -- a tampered or partially-edited JSON on disk fails
validation rather than silently replaying as if nothing changed.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Shared identifier rules
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")


def _looks_like_pii(value: str) -> bool:
    """Conservative heuristic for 'this literal looks like raw sensitive
    data, refuse to persist it in an artifact.' Deliberately narrow: it
    must not flag ordinary literals like route paths ('/members/search')
    or short IDs, only shapes that are unambiguously SSN- or PAN-like.
    """
    if _SSN_RE.match(value):
        return True
    digits_only = re.sub(r"[ \-]", "", value)
    return (
        digits_only.isdigit()
        and 13 <= len(digits_only) <= 19
        and digits_only == re.sub(r"[^0-9]", "", value)
    )


def _validate_identifier(v: str) -> str:
    if not _IDENTIFIER_RE.match(v):
        raise ValueError(
            f"'{v}' is not a valid snake_case identifier (expected pattern {_IDENTIFIER_RE.pattern})"
        )
    return v


# ---------------------------------------------------------------------------
# Typed input/output contract
# ---------------------------------------------------------------------------


class ParamType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"


class ParamSpec(BaseModel):
    """One typed input parameter the caller supplies per invocation."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: ParamType
    required: bool = True
    description: str = ""
    pattern: str | None = None
    enum_values: list[str] | None = None
    default: Any | None = None
    sensitive: bool = False

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, v: str) -> str:
        return _validate_identifier(v)

    @model_validator(mode="after")
    def _validate_shape(self) -> ParamSpec:
        if self.pattern is not None and self.type != ParamType.STRING:
            raise ValueError("'pattern' is only meaningful for type=string")
        if self.type == ParamType.ENUM and not self.enum_values:
            raise ValueError("type=enum requires a non-empty enum_values list")
        if self.type != ParamType.ENUM and self.enum_values is not None:
            raise ValueError("enum_values is only meaningful for type=enum")
        if self.sensitive and self.default is not None:
            raise ValueError(
                "a sensitive parameter must not declare a default/example value "
                "(it would bake example sensitive data into the artifact)"
            )
        return self


class OutputSpec(BaseModel):
    """One typed value the capability returns to the caller."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: ParamType
    description: str = ""
    sensitive: bool = False
    nullable: bool = False

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, v: str) -> str:
        return _validate_identifier(v)


# ---------------------------------------------------------------------------
# Locator: how a control is identified, with an ordered fallback ladder
# ---------------------------------------------------------------------------


class LocatorStrategy(str, Enum):
    ROLE_NAME = "role_name"
    LABEL_PROXIMITY = "label_proximity"
    ANCHORED_REGION = "anchored_region"
    VISUAL_TEMPLATE = "visual_template"  # tier 4: shape-validated, not executed (see cua.locator)


_STRATEGY_REQUIRED_PARAMS: dict[LocatorStrategy, frozenset] = {
    LocatorStrategy.ROLE_NAME: frozenset({"role", "name"}),
    LocatorStrategy.LABEL_PROXIMITY: frozenset({"near_text", "control_type"}),
    LocatorStrategy.ANCHORED_REGION: frozenset({"frame", "region", "index"}),
    LocatorStrategy.VISUAL_TEMPLATE: frozenset({"asset", "confidence_min"}),
}


class LocatorTier(BaseModel):
    """One rung of the locator fallback ladder.

    `params` is intentionally a strategy-tagged dict rather than a subclass
    per strategy: it keeps Target.fallbacks a single homogeneous list (easy
    to iterate at replay time) while `_validate_params` still enforces an
    exact, strategy-specific shape so a malformed locator fails at
    authoring/review time rather than silently at replay.
    """

    model_config = ConfigDict(extra="forbid")

    strategy: LocatorStrategy
    params: dict[str, Any]
    confidence_rationale: str = ""

    @model_validator(mode="after")
    def _validate_params(self) -> LocatorTier:
        required = _STRATEGY_REQUIRED_PARAMS[self.strategy]
        got = frozenset(self.params.keys())
        if got != required:
            missing = required - got
            extra = got - required
            parts = []
            if missing:
                parts.append(f"missing {sorted(missing)}")
            if extra:
                parts.append(f"unexpected {sorted(extra)}")
            raise ValueError(f"locator strategy '{self.strategy.value}' params invalid: {', '.join(parts)}")
        return self


class RecordedEvidence(BaseModel):
    """Diagnostic/operator-facing provenance for a target. Never the
    execution path -- replay resolves `Target.primary`/`fallbacks` only.
    """

    model_config = ConfigDict(extra="forbid")

    bbox: tuple[int, int, int, int] | None = None
    screenshot_ref: str | None = None
    dom_hint: str | None = None


class Target(BaseModel):
    """How to find one control, as an ordered set of tiers to try."""

    model_config = ConfigDict(extra="forbid")

    primary: LocatorTier
    fallbacks: list[LocatorTier] = Field(default_factory=list)
    recorded_evidence: RecordedEvidence | None = None
    ambiguity_policy: Literal["first_unique_match", "escalate_on_ambiguous"] = "escalate_on_ambiguous"


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    WAIT_FOR = "wait_for"
    EXTRACT = "extract"
    ASSERT_CHECKPOINT = "assert_checkpoint"
    DISMISS = "dismiss"


class RiskLevel(str, Enum):
    SAFE = "safe"  # read-only / reversible
    SENSITIVE = "sensitive"  # writes, but low blast-radius / reversible
    RISKY_IRREVERSIBLE = "risky_irreversible"  # requires conservative handling


_TARGETED_ACTIONS = frozenset(
    {
        ActionType.CLICK,
        ActionType.TYPE,
        ActionType.SELECT,
        ActionType.WAIT_FOR,
        ActionType.EXTRACT,
        ActionType.ASSERT_CHECKPOINT,
        ActionType.DISMISS,
    }
)
_VALUE_SOURCE_ACTIONS = frozenset({ActionType.TYPE, ActionType.SELECT})


class Step(BaseModel):
    """One ordered action in the recorded flow."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    action: ActionType
    target: Target | None = None
    input_param: str | None = None
    literal_value: str | None = None
    output_field: str | None = None
    risk: RiskLevel = RiskLevel.SAFE
    risk_rationale: str = ""
    timeout_ms: int = 5000
    max_retries: int = 0

    @field_validator("step_id")
    @classmethod
    def _step_id_is_identifier(cls, v: str) -> str:
        return _validate_identifier(v)

    @model_validator(mode="after")
    def _validate_shape(self) -> Step:
        action = self.action

        if action == ActionType.NAVIGATE:
            if self.literal_value is None and self.input_param is None:
                raise ValueError("navigate step requires a literal_value or input_param destination")
            if self.target is not None:
                raise ValueError("navigate step must not declare a target")
        elif action in _TARGETED_ACTIONS:
            if self.target is None:
                raise ValueError(f"{action.value} step requires a target")

        if action in _VALUE_SOURCE_ACTIONS:
            has_param = self.input_param is not None
            has_literal = self.literal_value is not None
            if has_param == has_literal:  # both set, or neither
                raise ValueError(
                    f"{action.value} step requires exactly one of input_param or literal_value"
                )

        if action == ActionType.EXTRACT and self.output_field is None:
            raise ValueError("extract step requires an output_field")

        if self.risk == RiskLevel.RISKY_IRREVERSIBLE and not self.risk_rationale.strip():
            raise ValueError("a risky_irreversible step requires a non-empty risk_rationale")

        if self.literal_value is not None and _looks_like_pii(self.literal_value):
            raise ValueError(
                "literal_value looks like raw sensitive data (SSN/PAN-shaped); "
                "parameterize it via input_param instead of persisting it in the artifact"
            )

        return self


# ---------------------------------------------------------------------------
# Known outcomes and checkpoint
# ---------------------------------------------------------------------------


class KnownOutcome(BaseModel):
    """A declared, expected-at-runtime state the replay engine recognizes
    by name. Declaring these on the artifact -- rather than leaving them to
    be discovered ad hoc in replay code -- is what lets the result contract
    distinguish a business outcome ('no such member') from a recoverable
    condition or a hard failure (see cua.replay).
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    description: str
    category: Literal["business_outcome", "recoverable", "hard_failure"]
    detection: LocatorTier

    @field_validator("code")
    @classmethod
    def _code_is_shouty_snake_case(cls, v: str) -> str:
        if not _CODE_RE.match(v):
            raise ValueError(f"'{v}' is not SHOUTY_SNAKE_CASE (expected pattern {_CODE_RE.pattern})")
        return v


class Checkpoint(BaseModel):
    """The success condition: how we know the goal was actually reached,
    rather than assuming the last action worked."""

    model_config = ConfigDict(extra="forbid")

    description: str
    detection: LocatorTier


# ---------------------------------------------------------------------------
# Policy, tenancy, and provenance
# ---------------------------------------------------------------------------


class PolicyScope(BaseModel):
    """The artifact's own allowlist footprint. Cross-checked against what
    the recorded steps actually do (see CapabilityArtifact validator) so
    the declaration can't silently under-report."""

    model_config = ConfigDict(extra="forbid")

    allowed_domains: list[str]
    allowed_action_types: list[ActionType]


class TenantScope(BaseModel):
    """Base capability vs. per-tenant override, for reuse across
    institutions running the same underlying vendor product.

    `tenant_id=None` marks a tenant-agnostic base artifact. A tenant-scoped
    artifact (tenant_id set) must point back to the base capability it
    specializes -- enforced at CapabilityArtifact level, since that's the
    layer that knows about both documents.
    """

    model_config = ConfigDict(extra="forbid")

    vendor_app_id: str
    base_capability_id: str | None = None
    tenant_id: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class ProvenanceRecordedBy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["llm_discovery", "human_authored", "migrated"]
    model: str | None = None
    discovery_run_id: str | None = None
    recorded_at: datetime


# ---------------------------------------------------------------------------
# The artifact
# ---------------------------------------------------------------------------


class CapabilityArtifact(BaseModel):
    """The agent-invocable capability: a typed, versioned, reviewable
    contract for a recorded flow. See module docstring for the shape.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    capability_id: str
    version: str
    description: str
    tenant_scope: TenantScope
    input_schema: list[ParamSpec] = Field(default_factory=list)
    output_schema: list[OutputSpec] = Field(default_factory=list)
    steps: list[Step] = Field(min_length=1)
    checkpoint: Checkpoint
    known_outcomes: list[KnownOutcome] = Field(default_factory=list)
    policy_scope: PolicyScope
    provenance: ProvenanceRecordedBy
    content_hash: str | None = Field(
        default=None,
        description=(
            "SHA-256 hex digest of the canonical JSON serialization of every "
            "field except content_hash itself. Omitted/None seals on "
            "construction; a present value is verified and rejected on mismatch."
        ),
    )

    @field_validator("capability_id")
    @classmethod
    def _capability_id_is_identifier(cls, v: str) -> str:
        return _validate_identifier(v)

    @field_validator("version")
    @classmethod
    def _version_is_semver(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(f"'{v}' is not a semver MAJOR.MINOR.PATCH string")
        return v

    @field_validator("content_hash")
    @classmethod
    def _content_hash_shape(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(r"[0-9a-f]{64}", v):
            raise ValueError("content_hash must be a 64-char lowercase hex SHA-256 digest")
        return v

    def compute_content_hash(self) -> str:
        """SHA-256 over canonical JSON of the artifact payload excluding
        `content_hash`. Stable across dump/load as long as the semantic
        fields are unchanged -- key order and separators are fixed here,
        independent of how a caller pretty-printed the file on disk.
        """
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def _validate_contract(self) -> CapabilityArtifact:
        ids = [s.step_id for s in self.steps]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate step_id(s): {dupes}")

        input_names = {p.name for p in self.input_schema}
        output_names = {o.name for o in self.output_schema}
        used_input_names: set = set()
        used_output_names: set = set()
        used_action_types: set = set()

        for s in self.steps:
            used_action_types.add(s.action)
            if s.input_param is not None:
                if s.input_param not in input_names:
                    raise ValueError(
                        f"step '{s.step_id}' references undeclared input_param '{s.input_param}'"
                    )
                used_input_names.add(s.input_param)
            if s.output_field is not None:
                if s.output_field not in output_names:
                    raise ValueError(
                        f"step '{s.step_id}' references undeclared output_field '{s.output_field}'"
                    )
                used_output_names.add(s.output_field)

        unused_inputs = sorted(input_names - used_input_names)
        if unused_inputs:
            raise ValueError(f"declared input(s) never used by any step: {unused_inputs}")

        required_outputs = {o.name for o in self.output_schema if not o.nullable}
        unproduced = sorted(required_outputs - used_output_names)
        if unproduced:
            raise ValueError(f"required output(s) never produced by any step: {unproduced}")

        declared_action_types = set(self.policy_scope.allowed_action_types)
        missing_from_policy = sorted(a.value for a in (used_action_types - declared_action_types))
        if missing_from_policy:
            raise ValueError(
                "policy_scope.allowed_action_types does not cover action type(s) "
                f"actually used by the recorded steps: {missing_from_policy}"
            )

        if self.tenant_scope.tenant_id and not self.tenant_scope.base_capability_id:
            raise ValueError(
                "a tenant-scoped artifact (tenant_id set) must declare base_capability_id"
            )

        expected = self.compute_content_hash()
        if self.content_hash is None:
            # Seal unsealed artifacts (fresh construction, or JSON written
            # before this field existed). Callers that edit a sealed artifact
            # in memory and re-validate must clear content_hash to reseal.
            self.content_hash = expected
        elif self.content_hash != expected:
            raise ValueError(
                "content_hash does not match artifact payload "
                f"(expected {expected}, got {self.content_hash})"
            )

        return self

    def to_log_safe_dict(self) -> dict:
        """A redacted projection safe to write to logs/evidence.

        Any recorded_evidence.dom_hint captured for a step that reads or
        writes a field marked `sensitive` is masked: the DOM snippet
        glimpsed during discovery could itself contain a real value. The
        screenshot pointer is left in place -- it is a reference, and
        redacting the *image itself* is the evidence-capture layer's job
        (see cua.evidence), not this schema's.
        """
        data = self.model_dump(mode="json")
        sensitive_names = {p.name for p in self.input_schema if p.sensitive} | {
            o.name for o in self.output_schema if o.sensitive
        }
        for step_data, step in zip(data["steps"], self.steps):
            touches_sensitive = (
                step.input_param is not None and step.input_param in sensitive_names
            ) or (step.output_field is not None and step.output_field in sensitive_names)
            target_data = step_data.get("target")
            if touches_sensitive and target_data and target_data.get("recorded_evidence"):
                target_data["recorded_evidence"]["dom_hint"] = "<redacted>"
        return data
