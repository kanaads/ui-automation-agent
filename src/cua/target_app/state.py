"""Per-app-instance state: seeded data, pending sub-account tokens, the
fault controller, and which tenant's branding to render. One `AppState`
per `create_app()` call -- never module-level globals -- so tests (and
two tenant instances running side by side) never bleed into each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cua.target_app.data import MemberStore, PendingSubAccountStore
from cua.target_app.faults import FaultController

DEFAULT_VARIANT = "base"

# Same underlying vendor product ("Meridian Core"), branded/labeled
# differently per tenant -- a stand-in for the real environment's
# hundreds of institutions on shared vendor software (assignment 3.7).
BRANDING = {
    "base": {
        "org_name": "Meridian Core Credit Union",
        "search_button_label": "Search",
    },
    "tenant_b": {
        "org_name": "Second Story Federal Credit Union",
        "search_button_label": "Find Member",
    },
}


@dataclass
class AppState:
    member_store: MemberStore
    pending: PendingSubAccountStore
    faults: FaultController
    tenant_variant: str
    branding: dict = field(default_factory=dict)

    @classmethod
    def fresh(cls, tenant_variant: str = DEFAULT_VARIANT) -> AppState:
        if tenant_variant not in BRANDING:
            raise ValueError(f"unknown tenant_variant '{tenant_variant}'")
        return cls(
            member_store=MemberStore(),
            pending=PendingSubAccountStore(),
            faults=FaultController(),
            tenant_variant=tenant_variant,
            branding=BRANDING[tenant_variant],
        )
