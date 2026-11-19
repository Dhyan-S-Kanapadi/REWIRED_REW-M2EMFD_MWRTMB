"""Offline, synthetic screenshot submissions for the local recording demo."""

import csv
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from backend.database import audited_transaction

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "payment_screenshots"


def submit_simulated(db, context, *, sender, content):
    if not db.execute("SELECT 1 FROM members WHERE id=?", (sender,)).fetchone():
        raise ValueError("Choose a demo member before uploading a screenshot.")
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(content).digest()
    # shortcut: only exact synthetic fixtures are extracted, add real OCR when the provider pipeline is ready.
    claim = next((item for item in manifest["images"]
                  if hashlib.sha256((FIXTURES / item["filename"]).read_bytes()).digest() == digest), None)
    if claim is None:
        raise ValueError("Use one of the supplied synthetic demo screenshots.")
    month, utr, amount = claim["expected_month"], claim["expected_utr_reference"], claim["claimed_amount"]
    if not db.execute("SELECT 1 FROM months WHERE month=?", (month,)).fetchone():
        raise ValueError("Load demo data before submitting a screenshot.")
    with (FIXTURES / manifest["bank_csv_reference"]).open(encoding="utf-8", newline="") as f:
        bank = next((row for row in csv.DictReader(f) if row["utr"] == utr), None)
    if bank is None:
        reason = "Synthetic bank CSV: no matching UTR; foreman review required."
    elif int(bank["amount_paise"]) != amount:
        reason = "Synthetic bank CSV: amount mismatch; foreman review required."
    elif sender != f"member-{int(bank['member_id'].split('-')[-1]):02}":
        reason = "Synthetic bank CSV: member mismatch; foreman review required."
    elif int(bank["month"]) != month:
        reason = "Synthetic bank CSV: month mismatch; foreman review required."
    else:
        reason = "Synthetic bank credit matches the screenshot."
    item_id = str(uuid4())
    with audited_transaction(db, context, actor=sender, reason=reason):
        db.execute("BEGIN IMMEDIATE")
        status = "needs_review"
        if reason == "Synthetic bank credit matches the screenshot.":
            if db.execute("SELECT 1 FROM ledger_entries WHERE kind='payment' AND member_id=? AND month=?", (sender, month)).fetchone():
                return {"bubbles": [{"type": "result_card", "status": "duplicate", "amount_paise": amount,
                                     "utr": utr, "reason": "Synthetic member and month already have a posted payment."}]}
            if db.execute("SELECT 1 FROM payments WHERE utr=? AND status='verified'", (utr,)).fetchone():
                return {"bubbles": [{"type": "result_card", "status": "duplicate", "amount_paise": amount,
                                     "utr": utr, "reason": "Synthetic bank credit was already used."}]}
            status = "verified"
        db.execute("INSERT INTO payments(id, member_id, month, amount_paise, utr, status) VALUES (?, ?, ?, ?, ?, ?)",
                   (item_id, sender, month, amount, utr, status))
        if status == "verified":
            db.execute("INSERT INTO ledger_entries(id, member_id, month, payment_id, amount_paise, kind) VALUES (?, ?, ?, ?, ?, 'payment')",
                       (str(uuid4()), sender, month, item_id, amount))
    return {"bubbles": [
        {"type": "text", "text": "SIMULATED: screenshot checked against the synthetic bank CSV."},
        {"type": "result_card", "status": status, "amount_paise": amount, "utr": utr, "reason": reason},
    ]}
