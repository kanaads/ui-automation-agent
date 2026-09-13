"""FaultController is the target app's fault-injection mechanism: it lets a
test (or the evidence-run script) arm a specific runtime condition -- a
session timeout, a permission denial, a slow load, a surprise interstitial,
a validation error -- to occur the next N times a given route is hit, for
a given browser session. This is what makes the "must accommodate errors
and exceptional states that legitimately occur at runtime" requirement
demonstrable on demand rather than a matter of luck.

Pure logic, no HTTP/FastAPI involved -- kept separate so it's trivially
unit-testable and reusable if the app grows more routes.
"""
import pytest

from cua.target_app.faults import ArmedFault, FaultCode, FaultController, HookPoint

pytestmark = pytest.mark.unit


def test_consume_with_nothing_armed_returns_none():
    fc = FaultController()
    assert fc.consume("session-a", HookPoint.SEARCH) is None


def test_arm_then_consume_returns_the_fault():
    fc = FaultController()
    fc.arm("session-a", HookPoint.DETAIL, FaultCode.SESSION_TIMEOUT)
    fault = fc.consume("session-a", HookPoint.DETAIL)
    assert fault is not None
    assert fault.code == FaultCode.SESSION_TIMEOUT


def test_default_occurrences_is_one_shot():
    fc = FaultController()
    fc.arm("session-a", HookPoint.DETAIL, FaultCode.PERMISSION_DENIED)
    assert fc.consume("session-a", HookPoint.DETAIL) is not None
    assert fc.consume("session-a", HookPoint.DETAIL) is None


def test_occurrences_greater_than_one_repeats_before_exhausting():
    fc = FaultController()
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.SLOW_LOAD, occurrences=2)
    assert fc.consume("session-a", HookPoint.SEARCH) is not None
    assert fc.consume("session-a", HookPoint.SEARCH) is not None
    assert fc.consume("session-a", HookPoint.SEARCH) is None


def test_delay_ms_carried_on_the_armed_fault():
    fc = FaultController()
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.SLOW_LOAD, delay_ms=250)
    fault = fc.consume("session-a", HookPoint.SEARCH)
    assert fault.delay_ms == 250


def test_faults_are_isolated_per_session():
    fc = FaultController()
    fc.arm("session-a", HookPoint.DETAIL, FaultCode.SESSION_TIMEOUT)
    assert fc.consume("session-b", HookPoint.DETAIL) is None
    assert fc.consume("session-a", HookPoint.DETAIL) is not None


def test_faults_are_isolated_per_hook_point():
    fc = FaultController()
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.SESSION_TIMEOUT)
    assert fc.consume("session-a", HookPoint.DETAIL) is None
    assert fc.consume("session-a", HookPoint.SEARCH) is not None


def test_queue_order_is_fifo_when_multiple_faults_armed():
    fc = FaultController()
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.SESSION_TIMEOUT)
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.PERMISSION_DENIED)
    first = fc.consume("session-a", HookPoint.SEARCH)
    second = fc.consume("session-a", HookPoint.SEARCH)
    assert first.code == FaultCode.SESSION_TIMEOUT
    assert second.code == FaultCode.PERMISSION_DENIED


def test_clear_hook_removes_only_that_hook():
    fc = FaultController()
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.SESSION_TIMEOUT)
    fc.arm("session-a", HookPoint.DETAIL, FaultCode.PERMISSION_DENIED)
    fc.clear("session-a", HookPoint.SEARCH)
    assert fc.consume("session-a", HookPoint.SEARCH) is None
    assert fc.consume("session-a", HookPoint.DETAIL) is not None


def test_clear_without_hook_removes_everything_for_the_session():
    fc = FaultController()
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.SESSION_TIMEOUT)
    fc.arm("session-a", HookPoint.DETAIL, FaultCode.PERMISSION_DENIED)
    fc.clear("session-a")
    assert fc.consume("session-a", HookPoint.SEARCH) is None
    assert fc.consume("session-a", HookPoint.DETAIL) is None


def test_list_armed_reflects_current_state():
    fc = FaultController()
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.SESSION_TIMEOUT, occurrences=3)
    armed = fc.list_armed("session-a")
    assert HookPoint.SEARCH in armed
    assert len(armed[HookPoint.SEARCH]) == 1
    assert armed[HookPoint.SEARCH][0].occurrences == 3


def test_list_armed_empty_for_unknown_session():
    fc = FaultController()
    assert fc.list_armed("nobody") == {}


def test_list_armed_omits_a_hook_once_its_queue_is_exhausted():
    fc = FaultController()
    fc.arm("session-a", HookPoint.SEARCH, FaultCode.SESSION_TIMEOUT)
    fc.consume("session-a", HookPoint.SEARCH)  # exhausts the one-shot fault
    assert fc.list_armed("session-a") == {}


def test_armed_fault_is_a_plain_value_object():
    f = ArmedFault(code=FaultCode.VALIDATION_ERROR, occurrences=1, delay_ms=0)
    assert f.code == FaultCode.VALIDATION_ERROR
