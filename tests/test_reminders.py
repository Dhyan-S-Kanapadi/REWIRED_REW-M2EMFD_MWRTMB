from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.database import audited_transaction, connect
from backend.ledger import post_verified_payment
from backend.main import app, scheduled_tick
from backend.reminders import private_bubbles, send_reminders
from test_contract import validator_for


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "reminders.db"
    db, context = connect(path)
    with audited_transaction(db, context, actor="foreman", reason="demo setup"):
        db.executemany("INSERT INTO members VALUES (?, ?)", [("m1", "Paid"), ("m2", "Unpaid")])
        db.execute("INSERT INTO months VALUES (1, '2026-12-03')")
        db.execute("INSERT INTO payments VALUES ('p1', 'm1', 1, 445001, '123456789012', 'verified')")
    post_verified_payment(db, context, "p1", actor="verifier", reason="matched bank")
    yield db, context, path
    db.close()


def test_scheduled_phases_private_and_deduplicated(store):
    db, context, _ = store
    assert send_reminders(db, context, actor="scheduler", today=date(2026, 11, 30)) == 0
    for day in (date(2026, 12, 1), date(2026, 12, 3), date(2026, 12, 4)):
        assert send_reminders(db, context, actor="scheduler", today=day) == 1
        assert send_reminders(db, context, actor="scheduler", today=day) == 0
    assert private_bubbles(db, "m1") == []
    assert [b["text"] for b in private_bubbles(db, "m2")] == ["Month 1 payment is due in 2 days.", "Month 1 payment is due today.", "Month 1 payment is overdue."]
    assert db.execute("SELECT COUNT(*) FROM audit_log WHERE action='reminders.insert'").fetchone()[0] == 3


def test_send_now_only_overdue_and_never_paid(store):
    db, context, _ = store
    assert send_reminders(db, context, actor="foreman", today=date(2026, 12, 3), send_now=True) == 0
    assert send_reminders(db, context, actor="foreman", today=date(2026, 12, 4), send_now=True) == 1
    assert send_reminders(db, context, actor="foreman", today=date(2026, 12, 4), send_now=True) == 0
    with pytest.raises(ValueError):
        send_reminders(db, context, actor="m2", today=date(2026, 12, 4), send_now=True)
    assert not private_bubbles(db, "m1")


def test_api_contract_and_member_filter(store, monkeypatch):
    db, context, path = store
    send_reminders(db, context, actor="foreman", today=date(2026, 12, 4), send_now=True)
    monkeypatch.setenv("CHITMIRROR_DATABASE", str(path))
    client = TestClient(app)
    member = client.get("/state", params={"role": "member", "member_id": "m2"})
    assert member.status_code == 200
    validator_for("state_response").validate(member.json())
    assert len(member.json()["private_bubbles"]) == 1
    paid = client.get("/state", params={"role": "member", "member_id": "m1"}).json()
    assert paid["private_bubbles"] == []
    assert member.json()["audit_log"] == member.json()["flags"] == member.json()["overdue"] == []
    foreman = client.get("/state", params={"role": "foreman"}).json()
    validator_for("state_response").validate(foreman)
    assert foreman["private_bubbles"] == []
    rejected = client.post("/reminders/send", json={"actor": "m2"})
    assert rejected.status_code == 422
    validator_for("error_response").validate(rejected.json())
    response = client.post("/reminders/send", json={"actor": "foreman"})
    assert response.status_code == 200
    validator_for("reminders_response").validate(response.json())


def test_paid_status_without_ledger_and_manual_approval_still_reminded(store):
    db, context, _ = store
    with audited_transaction(db, context, actor="foreman", reason="demo"):
        db.execute("INSERT INTO payments VALUES ('p2', 'm2', 1, 445002, '123456789013', 'manual_approved')")
    assert send_reminders(db, context, actor="foreman", today=date(2026, 12, 4), send_now=True) == 1


def test_scheduler_tick_and_send_now_endpoint(store, monkeypatch):
    db, context, path = store
    monkeypatch.setenv("CHITMIRROR_DATABASE", str(path))
    monkeypatch.setattr("backend.reminders.india_today", lambda: date(2026, 12, 4))
    scheduled_tick()
    assert len(private_bubbles(db, "m2")) == 1
    client = TestClient(app)
    response = client.post("/reminders/send", json={"actor": "foreman"})
    assert response.json() == {"sent": 0}
    validator_for("reminders_response").validate(response.json())
    monkeypatch.setattr("backend.reminders.india_today", lambda: date(2026, 12, 5))
    response = client.post("/reminders/send", json={"actor": "foreman"})
    assert response.json() == {"sent": 1}
    assert len(private_bubbles(db, "m2")) == 2
    assert private_bubbles(db, "m1") == []


def test_reminder_request_schema_is_strict():
    client = TestClient(app)
    invalid_payloads = [
        {},
        {"actor": ""},
        {"actor": 7},
        {"actor": "foreman", "extra": True},
    ]
    for payload in invalid_payloads:
        response = client.post("/reminders/send", json=payload)
        assert response.status_code == 422
        validator_for("error_response").validate(response.json())
