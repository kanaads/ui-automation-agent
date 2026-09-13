"""Assignment 3.4: 'Never persist secrets or raw sensitive data into
artifacts or logs. Redact appropriately.'

At the artifact layer this shows up two ways:
  1. Structural prevention: a Step's literal_value can never look like PII
     (covered in test_step.py) and a sensitive ParamSpec can never carry a
     baked-in default/example (covered in test_param_spec.py).
  2. A `to_log_safe_dict()` projection that any logger/evidence-writer can
     call before persisting the artifact, so recorded_evidence captured
     for a sensitive-bound step never carries a raw DOM snippet that might
     itself contain a real value glimpsed during discovery.
"""
import pytest

from cua.artifact.models import (
    ActionType,
    LocatorStrategy,
    LocatorTier,
    RecordedEvidence,
    RiskLevel,
    Step,
    Target,
)

pytestmark = pytest.mark.unit


def test_log_safe_dict_redacts_recorded_evidence_for_sensitive_bound_steps(sample_artifact):
    safe = sample_artifact.to_log_safe_dict()
    steps_by_id = {s["step_id"]: s for s in safe["steps"]}

    balance_step = steps_by_id["s4_extract_balance"]  # output_field=savings_balance, sensitive=True
    assert balance_step["target"]["recorded_evidence"]["dom_hint"] == "<redacted>"
    # the screenshot pointer is kept -- it's a reference, not the raw value,
    # and evidence capture (Phase 9) is responsible for redacting the image itself.
    assert balance_step["target"]["recorded_evidence"]["screenshot_ref"] == "step_03.png"


def test_log_safe_dict_leaves_non_sensitive_steps_untouched(sample_artifact):
    safe = sample_artifact.to_log_safe_dict()
    steps_by_id = {s["step_id"]: s for s in safe["steps"]}
    navigate_step = steps_by_id["s1_navigate"]
    assert navigate_step["literal_value"] == "/members/search"


def test_log_safe_dict_marks_sensitive_input_params(sample_artifact):
    safe = sample_artifact.to_log_safe_dict()
    balance_output = next(o for o in safe["output_schema"] if o["name"] == "savings_balance")
    assert balance_output["sensitive"] is True


def test_log_safe_dict_is_json_serializable(sample_artifact):
    import json

    json.dumps(sample_artifact.to_log_safe_dict())


def test_step_recorded_evidence_with_no_sensitive_binding_keeps_dom_hint():
    target = Target(
        primary=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "button", "name": "Search"}),
        recorded_evidence=RecordedEvidence(dom_hint="input[name=btnSrch]", screenshot_ref="s.png"),
    )
    step = Step(step_id="s1", action=ActionType.CLICK, target=target, risk=RiskLevel.SAFE)
    assert step.target.recorded_evidence.dom_hint == "input[name=btnSrch]"
