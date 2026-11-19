from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.database import audited_transaction, connect


def test_simulated_screenshot_to_review_and_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITMIRROR_DATABASE", str(tmp_path / "demo.db"))
    monkeypatch.setenv("CHITMIRROR_SIMULATED_DEMO", "1")
    client = TestClient(app)
    assert client.post("/demo/load", json={"actor": "foreman"}).status_code == 200
    fixtures = Path("tests/fixtures/payment_screenshots")
    image = fixtures / "fake/gpay/t07-fake-gpay-001.png"
    sample = client.get("/demo/screenshot")
    assert sample.status_code == 200 and sample.content == image.read_bytes()
    result = client.post("/message", data={"sender": "member-07", "text": ""},
                         files={"image": ("anything.png", sample.content, "image/png")})
    assert result.status_code == 200
    card = result.json()["bubbles"][1]
    assert card["status"] == "needs_review" and "no matching UTR" in card["reason"]
    state = client.get("/state", params={"role": "foreman"}).json()
    flag = next(x for x in state["flags"] if x["member_id"] == "member-07")
    assert "no matching UTR" in flag["reason"]
    assert any(a["actor"] == "member-07" and "no matching UTR" in a["reason"] for a in state["audit_log"])
    review = client.post("/review", json={"actor": "foreman", "item_id": flag["item_id"], "decision": "reject", "reason": "No bank credit"})
    assert review.status_code == 200
    assert not any(x["item_id"] == flag["item_id"] for x in client.get("/state", params={"role": "foreman"}).json()["flags"])
    unknown = client.post("/message", data={"sender": "member-07"}, files={"image": ("fake.png", b"unknown", "image/png")})
    assert unknown.status_code == 422


def test_matching_and_amount_mismatch_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITMIRROR_DATABASE", str(tmp_path / "demo.db"))
    monkeypatch.setenv("CHITMIRROR_SIMULATED_DEMO", "1")
    client = TestClient(app)
    db, context = connect(str(tmp_path / "demo.db"))
    with audited_transaction(db, context, actor="foreman", reason="Set up synthetic demo"):
        db.execute("INSERT INTO members VALUES ('member-07', 'Member 07')")
        db.execute("INSERT INTO months VALUES (3, '2026-03-10')")
    db.close()
    for scenario, expected in (("matching", "credit matches"), ("mismatch", "amount mismatch")):
        sample = client.get("/demo/screenshot", params={"scenario": scenario})
        assert sample.status_code == 200
        result = client.post("/message", data={"sender": "member-07"}, files={"image": ("demo.png", sample.content, "image/png")})
        assert result.status_code == 200
        assert expected in result.json()["bubbles"][1]["reason"]
        assert result.json()["bubbles"][1]["status"] == ("verified" if scenario == "matching" else "needs_review")
    flags = client.get("/state", params={"role": "foreman"}).json()["flags"]
    assert len(flags) == 1 and "amount mismatch" in flags[0]["reason"]
    state = client.get("/state", params={"role": "foreman"}).json()
    assert state["ledger"][0]["status"] == "verified" and state["counters"]["paid"] == 1
    matching = client.get("/demo/screenshot", params={"scenario": "matching"})
    duplicate = client.post("/message", data={"sender": "member-07"}, files={"image": ("demo.png", matching.content, "image/png")})
    assert duplicate.json()["bubbles"][0]["status"] == "duplicate"
    assert client.get("/demo/screenshot", params={"scenario": "unknown"}).status_code == 404
