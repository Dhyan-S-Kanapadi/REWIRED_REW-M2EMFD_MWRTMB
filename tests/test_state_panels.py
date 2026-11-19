from datetime import date

import pytest

from backend.database import audited_transaction, connect
from backend.ledger import post_verified_payment
from backend.main import app
from backend.state import get_state
from test_contract import validator_for


@pytest.fixture
def panel_store(tmp_path, monkeypatch):
    path = tmp_path / "state_panels.db"
    db, context = connect(path)
    monkeypatch.setattr("backend.state.india_today", lambda: date(2026, 4, 2))
    with audited_transaction(db, context, actor="foreman", reason="panel setup"):
        db.executemany("INSERT INTO members VALUES (?, ?)", [("m1", "Member One"), ("m2", "Member Two")])
        db.executemany("INSERT INTO months VALUES (?, ?)", [(1, "2026-02-01"), (2, "2026-04-01")])
        db.executemany("INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?)", [
            ("p1", "m1", 1, 445000, "123456789012", "needs_review"),
            ("p2", "m1", 2, 445000, "123456789013", "verified"),
            ("p3", "m2", 2, 445000, "123456789014", "verified"),
        ])
    post_verified_payment(db, context, "p2", actor="verifier", reason="matched bank")
    post_verified_payment(db, context, "p3", actor="verifier", reason="matched bank")
    yield db
    db.close()


def test_state_panels_use_real_data_and_overdue_counter_matches_list(panel_store):
    state = get_state(panel_store, role="foreman")
    validator_for("state_response").validate(state)

    assert len(state["flags"]) == 1
    assert state["flags"][0]["item_id"] == "p1"
    assert "needs_review" in state["flags"][0]["reason"]
    assert "123456789012" in state["flags"][0]["reason"]
    assert len(state["overdue"]) == 2
    assert state["counters"]["overdue"] == len(state["overdue"])
    assert {entry["member_id"] for entry in state["overdue"]} == {"m1", "m2"}


def test_member_state_does_not_expose_foreman_panels(panel_store):
    state = get_state(panel_store, role="member", member_id="m1")
    validator_for("state_response").validate(state)

    assert state["flags"] == []
    assert state["overdue"] == []
    assert state["audit_log"] == []


def test_no_audit_mutation_route_is_exposed():
    exposed = {
        (getattr(route, "path", ""), method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert not any(
        "audit" in path and method in {"POST", "PUT", "PATCH", "DELETE"}
        for path, method in exposed
    )
