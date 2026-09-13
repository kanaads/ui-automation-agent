"""'Meridian Core' (mock): a deliberately hostile legacy credit-union
back-office proxy target.

Hostile on purpose: nested iframes instead of a single clean page (a
classic HTML `<frameset>` renders unreliably in headless Chromium, so two
named iframes -- nav + content -- stand in for it while posing the same
"which frame is this control in" problem), table-based layout, no
`id`/`data-testid`/`<label for>` anywhere, legacy `<font>`/`bgcolor`
styling. A couple of anchor points (page headings, submit-button values)
are left with real accessible semantics -- a real enterprise app is ugly,
not universally illegible even to its own users.

Two flows:
  - search -> detail (read-only: look up a member, read their balance)
  - subaccount new -> confirm -> commit (multi-field form with a
    confirmation step; the final commit is the RISKY_IRREVERSIBLE action
    a recorded capability should stop short of by default)

Fault injection (see cua.target_app.faults) lets a test or the
evidence-run script make a specific runtime condition -- session
timeout, permission denial, slow load, a surprise interstitial, a forced
validation error -- occur on demand at a specific route, for a specific
browser session, so the "must accommodate real runtime errors" half of
the assignment is demonstrable rather than a matter of luck.

`/debug/*` is test/evidence infrastructure, not part of the agent-facing
surface -- Phase 6's allowlist explicitly excludes it.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from cua.target_app.data import PendingSubAccountStore
from cua.target_app.faults import ArmedFault, FaultCode, FaultController, HookPoint
from cua.target_app.state import DEFAULT_VARIANT, AppState

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

SESSION_COOKIE = "sid"
MIN_INITIAL_DEPOSIT_CENTS = 2500  # $25.00

# Form fields default to "" rather than being framework-required: a real
# browser always submits a text field's name even when empty, but we treat
# "present but blank" as an application-level validation concern (matching
# how the legacy app itself would behave) rather than a framework 422 --
# which also sidesteps a test-client quirk where an empty form value can be
# omitted from the encoded body entirely.


def format_cents(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def get_session_id(request: Request, response: Response) -> str:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        sid = uuid.uuid4().hex
        response.set_cookie(SESSION_COOKIE, sid, httponly=True)
    return sid


SessionId = Annotated[str, Depends(get_session_id)]


def _state(request: Request) -> AppState:
    return request.app.state.cua_state


def check_fault(state: AppState, session_id: str, hook: HookPoint) -> ArmedFault | None:
    return state.faults.consume(session_id, hook)


def render_generic_fault(
    request: Request, fault: ArmedFault, *, resume_to: str, branding: dict
) -> Response | None:
    """Renders the faults whose presentation is content-agnostic. Returns
    None when the caller must render it itself (VALIDATION_ERROR needs
    the caller's form context) or after a SLOW_LOAD delay has elapsed
    (caller should proceed normally)."""
    if fault.code == FaultCode.SESSION_TIMEOUT:
        return templates.TemplateResponse(
            request, "session_timeout.html", {"resume_to": resume_to, "branding": branding}
        )
    if fault.code == FaultCode.PERMISSION_DENIED:
        return templates.TemplateResponse(request, "permission_denied.html", {"branding": branding})
    if fault.code == FaultCode.SURPRISE_DIALOG:
        return templates.TemplateResponse(
            request, "surprise_dialog.html", {"resume_to": resume_to, "branding": branding}
        )
    if fault.code == FaultCode.SLOW_LOAD:
        time.sleep(fault.delay_ms / 1000)
        return None
    return None  # VALIDATION_ERROR: caller's job


# ---------------------------------------------------------------------------
# Main (agent-facing) router
# ---------------------------------------------------------------------------

router = APIRouter()


@router.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/app")


@router.get("/app")
def get_app_shell(
    request: Request, session_id: SessionId, start: str = "/content/search"
) -> Response:
    state = _state(request)
    return templates.TemplateResponse(request, "shell.html", {"branding": state.branding, "start": start})


@router.get("/nav")
def get_nav(request: Request, session_id: SessionId) -> Response:
    state = _state(request)
    return templates.TemplateResponse(request, "nav.html", {"branding": state.branding})


@router.get("/content/search")
def get_search(request: Request, session_id: SessionId, notfound: bool = False) -> Response:
    state = _state(request)
    fault = check_fault(state, session_id, HookPoint.SEARCH)
    if fault:
        resp = render_generic_fault(request, fault, resume_to="/content/search", branding=state.branding)
        if resp is not None:
            return resp
    return templates.TemplateResponse(
        request, "search_content.html", {"branding": state.branding, "notfound": notfound}
    )


@router.post("/content/search")
def post_search(
    request: Request,
    session_id: SessionId,
    txtMemberId: str = Form(""),
) -> Response:
    state = _state(request)
    fault = check_fault(state, session_id, HookPoint.SEARCH)
    if fault:
        resp = render_generic_fault(request, fault, resume_to="/content/search", branding=state.branding)
        if resp is not None:
            return resp

    member = state.member_store.get(txtMemberId.strip())
    if member is None:
        return templates.TemplateResponse(
            request, "search_content.html", {"branding": state.branding, "notfound": True}
        )
    return RedirectResponse(url=f"/content/detail?id={member.member_id}", status_code=303)


@router.get("/content/detail")
def get_detail(request: Request, id: str, session_id: SessionId) -> Response:
    state = _state(request)
    resume_to = f"/content/detail?id={id}"
    fault = check_fault(state, session_id, HookPoint.DETAIL)
    if fault:
        resp = render_generic_fault(request, fault, resume_to=resume_to, branding=state.branding)
        if resp is not None:
            return resp

    member = state.member_store.get(id)
    if member is None:
        return templates.TemplateResponse(
            request, "search_content.html", {"branding": state.branding, "notfound": True}
        )
    return templates.TemplateResponse(
        request,
        "detail_content.html",
        {
            "branding": state.branding,
            "member": member,
            "balance_display": format_cents(member.savings_balance_cents),
        },
    )


@router.get("/content/subaccount/new")
def get_subaccount_new(request: Request, id: str, session_id: SessionId) -> Response:
    state = _state(request)
    member = state.member_store.get(id)
    if member is None:
        return templates.TemplateResponse(
            request, "search_content.html", {"branding": state.branding, "notfound": True}
        )
    return templates.TemplateResponse(
        request,
        "subaccount_new.html",
        {"branding": state.branding, "member": member, "errors": [], "values": {}},
    )


@router.post("/content/subaccount/new")
def post_subaccount_new(
    request: Request,
    session_id: SessionId,
    id: str = Form(""),
    selAcctType: str = Form(""),
    txtInitialDeposit: str = Form(""),
    txtPurpose: str = Form(""),
) -> Response:
    state = _state(request)
    member = state.member_store.get(id)
    resume_to = f"/content/subaccount/new?id={id}"

    forced_validation_error = False
    fault = check_fault(state, session_id, HookPoint.SUBACCOUNT_NEW_SUBMIT)
    if fault:
        resp = render_generic_fault(request, fault, resume_to=resume_to, branding=state.branding)
        if resp is not None:
            return resp
        if fault.code == FaultCode.VALIDATION_ERROR:
            forced_validation_error = True

    values = {
        "selAcctType": selAcctType,
        "txtInitialDeposit": txtInitialDeposit,
        "txtPurpose": txtPurpose,
    }
    errors: list[str] = []
    deposit_cents: int | None = None

    if forced_validation_error:
        errors.append("Initial deposit must be at least $25.00.")
    else:
        try:
            deposit_cents = round(float(txtInitialDeposit.strip()) * 100)
        except ValueError:
            errors.append("Initial deposit must be a valid dollar amount.")
        else:
            if deposit_cents < MIN_INITIAL_DEPOSIT_CENTS:
                errors.append("Initial deposit must be at least $25.00.")
        if not txtPurpose.strip():
            errors.append("Purpose is required.")
        if selAcctType not in ("SAVINGS", "CHECKING"):
            errors.append("Account type is invalid.")

    if errors:
        return templates.TemplateResponse(
            request,
            "subaccount_new.html",
            {"branding": state.branding, "member": member, "errors": errors, "values": values},
        )

    # No errors means the try/except above ran to completion and set this.
    assert deposit_cents is not None

    token = state.pending.create(
        member_id=id,
        account_type=selAcctType,
        initial_deposit_cents=deposit_cents,
        purpose=txtPurpose.strip(),
    )
    pending = state.pending.get(token)
    return templates.TemplateResponse(
        request,
        "subaccount_confirm.html",
        {"branding": state.branding, "member": member, "pending": pending, "token": token},
    )


@router.post("/content/subaccount/confirm")
def post_subaccount_confirm(
    request: Request, session_id: SessionId, token: str = Form("")
) -> Response:
    state = _state(request)
    fault = check_fault(state, session_id, HookPoint.SUBACCOUNT_CONFIRM)
    if fault:
        resp = render_generic_fault(
            request, fault, resume_to="/content/subaccount/new", branding=state.branding
        )
        if resp is not None:
            return resp

    pending = state.pending.consume(token)
    if pending is None:
        return templates.TemplateResponse(request, "subaccount_expired.html", {"branding": state.branding})

    account_number = f"SA-{token[:6].upper()}"
    return templates.TemplateResponse(
        request,
        "subaccount_success.html",
        {"branding": state.branding, "account_number": account_number, "pending": pending},
    )


# ---------------------------------------------------------------------------
# Debug / evidence-capture router (NOT part of the agent-facing allowlist)
# ---------------------------------------------------------------------------

debug_router = APIRouter()


class ArmFaultBody(BaseModel):
    hook: HookPoint
    code: FaultCode
    occurrences: int = 1
    delay_ms: int = 0


class ClearFaultBody(BaseModel):
    hook: HookPoint | None = None


@debug_router.post("/faults/arm")
def arm_fault(body: ArmFaultBody, request: Request, session_id: SessionId) -> dict:
    state = _state(request)
    state.faults.arm(session_id, body.hook, body.code, occurrences=body.occurrences, delay_ms=body.delay_ms)
    return {"ok": True}


@debug_router.post("/faults/clear")
def clear_faults(body: ClearFaultBody, request: Request, session_id: SessionId) -> dict:
    state = _state(request)
    state.faults.clear(session_id, body.hook)
    return {"ok": True}


@debug_router.get("/faults")
def list_faults(request: Request, session_id: SessionId) -> dict:
    state = _state(request)
    armed = state.faults.list_armed(session_id)
    return {
        hook.value: [{"code": f.code.value, "occurrences": f.occurrences, "delay_ms": f.delay_ms} for f in lst]
        for hook, lst in armed.items()
    }


@debug_router.post("/reset")
def reset_state(request: Request) -> dict:
    state = _state(request)
    state.member_store.reset()
    state.pending = PendingSubAccountStore()
    state.faults = FaultController()
    return {"ok": True}


def create_app(tenant_variant: str = DEFAULT_VARIANT) -> FastAPI:
    app = FastAPI(title="Meridian Core (mock)")
    app.state.cua_state = AppState.fresh(tenant_variant)
    app.include_router(router)
    app.include_router(debug_router, prefix="/debug")
    return app
