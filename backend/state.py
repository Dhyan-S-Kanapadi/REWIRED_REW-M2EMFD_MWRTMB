"""Read-only dashboard state; identity selectors are for the demo only."""

from backend.ledger import member_statement
from backend.reminders import india_today, private_bubbles


def get_state(db, *, role, member_id=None):
    if role not in {"foreman", "member"} or (role == "member" and not member_id):
        raise ValueError("valid role and member ID required")
    members = [{"id": r[0], "name": r[1]} for r in db.execute("SELECT id, name FROM members ORDER BY id")]
    if role == "member" and member_id not in {m["id"] for m in members}:
        raise ValueError("member not found")
    months = db.execute("SELECT month, due_date FROM months ORDER BY month").fetchall()
    today = india_today().isoformat()
    ledger, flags, overdue = [], [], []
    for month, due in months:
        for member in members:
            member_key = member["id"]
            row = db.execute("""
                SELECT p.id, p.status, p.amount_paise, p.utr,
                       EXISTS(SELECT 1 FROM ledger_entries l WHERE l.payment_id=p.id AND l.kind='payment')
                FROM payments p WHERE p.member_id=? AND p.month=?
                ORDER BY CASE WHEN p.status='verified' THEN 0 WHEN p.status='needs_review' THEN 1 ELSE 2 END, p.rowid DESC LIMIT 1
            """, (member_key, month)).fetchone()
            status, amount, utr = ("overdue" if due < today else "pending"), 0, None
            if row:
                item, payment_status, amount, raw_utr, posted = row
                utr = raw_utr if raw_utr and len(raw_utr) == 12 and raw_utr.isascii() and raw_utr.isdigit() else None
                if payment_status == "verified" and posted:
                    status = "verified"
                elif payment_status in ("needs_review", "manual_approved"):
                    status = "needs_review"
                elif payment_status == "rejected":
                    status = "rejected"
            entry = {"member_id": member_key, "month": month, "status": status, "amount_paise": amount, "utr": utr}
            ledger.append(entry)
            if due < today and status != "verified":
                overdue.append(entry)
    current = months[-1][0] if months else None
    flags = [{"item_id": r[0], "member_id": r[1], "month": r[2], "reason": r[3] or "Payment requires review"}
             for r in db.execute("""
                SELECT p.id, p.member_id, p.month,
                    (SELECT a.reason FROM audit_log a WHERE a.entity_id=p.id AND a.action='payments.insert' ORDER BY a.id DESC LIMIT 1)
                FROM payments p WHERE p.status='needs_review' ORDER BY p.rowid DESC
             """)]
    current_ledger = [entry for entry in ledger if entry["month"] == current]
    audit = [{"id": str(r[0]), "actor": r[1], "action": r[2], "reason": r[3], "timestamp": r[4]}
             for r in db.execute("SELECT id, actor, action, reason, timestamp FROM audit_log ORDER BY id")]
    return {"members": members, "months": [m[0] for m in months], "ledger": ledger,
            "counters": {"collected_paise": sum(e["amount_paise"] for e in current_ledger if e["status"] == "verified"),
                         "paid": sum(e["status"] == "verified" for e in current_ledger), "total_members": len(members),
                         "needs_review": sum(e["status"] == "needs_review" for e in current_ledger),
                         "overdue": sum(e["month"] == current for e in overdue)},
            "flags": flags if role == "foreman" else [], "overdue": overdue if role == "foreman" else [],
            "audit_log": audit if role == "foreman" else [],
            "statement": member_statement(db, member_id) if role == "member" else [],
            "private_bubbles": private_bubbles(db, member_id) if role == "member" else []}
