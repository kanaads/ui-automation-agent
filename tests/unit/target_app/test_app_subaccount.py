"""The sub-account flow: new -> confirm -> commit. This is the
multi-field-form-with-confirmation-step half of the assignment's suggested
target shape, and the natural home of a RISKY_IRREVERSIBLE step (the final
commit) that a recorded capability should stop short of by default.
"""
import pytest

pytestmark = pytest.mark.unit


def test_new_subaccount_form_renders_for_a_known_member(client):
    resp = client.get("/content/subaccount/new", params={"id": "10001"})
    assert resp.status_code == 200
    assert "Open New Sub-Account" in resp.text
    assert 'name="selAcctType"' in resp.text
    assert 'name="txtInitialDeposit"' in resp.text
    assert 'name="txtPurpose"' in resp.text


def test_new_subaccount_form_for_unknown_member_falls_back_to_not_found(client):
    resp = client.get("/content/subaccount/new", params={"id": "00000000"})
    assert resp.status_code == 200
    assert "No records match your search." in resp.text


def test_invalid_account_type_is_a_validation_error(client):
    resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "CRYPTO",
            "txtInitialDeposit": "100.00",
            "txtPurpose": "x",
        },
    )
    assert resp.status_code == 200
    assert "Account type is invalid." in resp.text


def test_valid_submission_reaches_confirmation_screen(client):
    resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "SAVINGS",
            "txtInitialDeposit": "100.00",
            "txtPurpose": "Vacation fund",
        },
    )
    assert resp.status_code == 200
    assert "Confirm New Sub-Account" in resp.text
    assert "Vacation fund" in resp.text
    assert "$100.00" in resp.text
    assert 'name="token"' in resp.text


def test_deposit_below_minimum_is_a_validation_error_not_a_crash(client):
    resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "SAVINGS",
            "txtInitialDeposit": "5.00",
            "txtPurpose": "Too small",
        },
    )
    assert resp.status_code == 200
    assert "at least $25.00" in resp.text
    # form is re-shown with the entered values preserved
    assert 'value="5.00"' in resp.text
    assert 'value="Too small"' in resp.text


def test_non_numeric_deposit_is_a_validation_error(client):
    resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "SAVINGS",
            "txtInitialDeposit": "not-a-number",
            "txtPurpose": "x",
        },
    )
    assert resp.status_code == 200
    assert "valid dollar amount" in resp.text


def test_missing_purpose_is_a_validation_error(client):
    resp = client.post(
        "/content/subaccount/new",
        data={"id": "10001", "selAcctType": "SAVINGS", "txtInitialDeposit": "100.00", "txtPurpose": ""},
    )
    assert resp.status_code == 200
    assert "Purpose is required." in resp.text


def test_confirm_commits_and_returns_success(client):
    new_resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "CHECKING",
            "txtInitialDeposit": "250.00",
            "txtPurpose": "Rent",
        },
    )
    token = _extract_token(new_resp.text)
    confirm_resp = client.post("/content/subaccount/confirm", data={"token": token})
    assert confirm_resp.status_code == 200
    assert "Sub-Account Opened" in confirm_resp.text
    assert "SA-" in confirm_resp.text


def test_confirm_token_is_one_time_use(client):
    new_resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "SAVINGS",
            "txtInitialDeposit": "100.00",
            "txtPurpose": "Rent",
        },
    )
    token = _extract_token(new_resp.text)
    first = client.post("/content/subaccount/confirm", data={"token": token})
    assert "Sub-Account Opened" in first.text
    second = client.post("/content/subaccount/confirm", data={"token": token})
    assert second.status_code == 200
    assert "expired" in second.text.lower()


def test_unknown_confirm_token_is_a_clear_result_not_a_crash(client):
    resp = client.post("/content/subaccount/confirm", data={"token": "bogus-token"})
    assert resp.status_code == 200
    assert "expired" in resp.text.lower()


def _extract_token(html: str) -> str:
    marker = 'name="token" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]
