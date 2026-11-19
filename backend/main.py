"""Development entry point; business endpoints belong to their own issues."""

import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
from pathlib import Path
import json
import hashlib
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.datastructures import UploadFile

from backend.database import connect, audited_transaction
from backend.messages import handle_message
from backend.demo import load_demo
from backend.reminders import send_reminders
from backend.state import get_state
from backend.provider_smoke import ProviderSmokeError
from backend.screenshot_reader import ScreenshotClaim, read_uploaded_screenshot
from backend.payment_checks import ExtractedPaymentClaim, InMemoryImageHashRegistry, load_bank_evidence, validate_payment_claim
from backend.ledger import post_verified_payment
from backend.review import review_payment
import httpx

ROOT = Path(__file__).resolve().parent.parent
_IMAGE_HASH_REGISTRY = InMemoryImageHashRegistry()
def database_path():
    return os.environ.get("CHITMIRROR_DATABASE", str(ROOT / "data" / "chitmirror.db"))


def scheduled_tick():
    db, context = connect(database_path())
    try:
        send_reminders(db, context, actor="scheduler")
    finally:
        db.close()


async def scheduler():
    while True:
        try:
            await asyncio.to_thread(scheduled_tick)
        except Exception:
            logging.exception("Reminder scheduler failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(scheduler())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="ChitMirror", version="0.0.1", lifespan=lifespan)


class ReminderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender: str
    text: str


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str
    item_id: str
    decision: str
    reason: str


class DemoLoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Invalid request."}})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config.js")
def frontend_config():
    api_base = os.environ.get("CHITMIRROR_API_BASE", "")
    return Response(f"window.CHITMIRROR_API_BASE = {json.dumps(api_base)};", media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.post("/reminders/send")
def reminders_send(payload: ReminderRequest):
    if payload.actor != "foreman":
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Foreman required."}})
    db, context = connect(database_path())
    try:
        return {"sent": send_reminders(db, context, actor=payload.actor, send_now=True)}
    finally:
        db.close()


@app.post("/review")
def review(payload: ReviewRequest):
    db, context = connect(database_path())
    try:
        try:
            return review_payment(db, context, item_id=payload.item_id, decision=payload.decision, actor=payload.actor, reason=payload.reason)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": str(exc)}})
    finally:
        db.close()


@app.post("/message")
async def message(request: Request):
    """Route member text commands and screenshot claims through the shared backend contract."""
    content_type = request.headers.get("content-type", "")
    image = None
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        if set(form.keys()) - {"sender", "text", "image"}:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Unexpected message fields."}})
        sender = str(form.get("sender", "")).strip()
        text = str(form.get("text", ""))
        image = form.get("image")
        if not hasattr(image, "read"):
            image = None
    else:
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Expected JSON or multipart form data."}})
        if not isinstance(payload, dict) or set(payload) - {"sender", "text"}:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Unexpected message fields."}})
        sender = str(payload.get("sender", "")).strip()
        text = str(payload.get("text", ""))
    if not sender:
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Sender is required."}})
    if image is None:
        if not text.strip():
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Message text is required."}})
        db, _ = connect(database_path())
        try:
            try:
                return handle_message(db, sender=sender, text=text)
            except ValueError as exc:
                return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": str(exc)}})
        finally:
            db.close()
    if sender == "foreman":
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Select the member shown on the payment screenshot."}})
    upload = await image.read()
    if not upload or len(upload) > 10 * 1024 * 1024:
        return JSONResponse(status_code=413, content={"error": {"code": "invalid_upload", "message": "Screenshot must be between 1 byte and 10 MB."}})
    filename = getattr(image, "filename", "") or "screenshot.png"
    if Path(filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return JSONResponse(status_code=415, content={"error": {"code": "invalid_upload", "message": "Use a PNG, JPG, or WebP screenshot."}})
    image_hash = hashlib.sha256(upload).hexdigest()
    read_error = None
    try:
        with httpx.Client() as client:
            claim = await asyncio.to_thread(read_uploaded_screenshot, filename, upload, client)
    except ProviderSmokeError as exc:
        claim = ScreenshotClaim(None, None, None, None, None, None, None, None)
        read_error = str(exc)
    db, context = connect(database_path())
    payment_id = str(uuid4())
    try:
        if db.execute("SELECT 1 FROM members WHERE id = ?", (sender,)).fetchone() is None:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Select a known group member."}})
        group = json.loads((ROOT / "data" / "demo_chit.json").read_text(encoding="utf-8"))["group"]
        used_utrs = {row[0] for row in db.execute("SELECT utr FROM payments WHERE utr IS NOT NULL")}
        evidence = load_bank_evidence(ROOT / "data" / "bank.csv")
        extracted = ExtractedPaymentClaim(
            member_id=sender, utr=claim.utr, amount_paise=claim.amount_paise,
            receiver_upi_id=claim.payee, image_sha256=image_hash,
        )
        report = validate_payment_claim(
            extracted, expected_amount_paise=int(group["base_instalment_paise"]),
            expected_receiver_upi_id=group["group_upi_id"], evidence_by_utr=evidence,
            used_utrs=used_utrs, image_hash_registry=_IMAGE_HASH_REGISTRY,
        )
        if read_error:
            status = "needs_review"
            reason = "Screenshot reader unavailable; manual review is required."
        elif report.by_name("utr_uniqueness").code == "duplicate_utr" or report.by_name("image_uniqueness").code == "duplicate_image":
            status = "duplicate"
            reason = "Transaction reference or screenshot was already submitted."
        elif report.by_name("expected_amount").code == "wrong_amount" or report.by_name("bank_evidence").code == "bank_amount_conflict":
            status = "wrong_amount"
            reason = "Amount does not match the instalment and independent bank evidence."
        elif report.passed and claim.readers_agree is True and claim.confidence is not None and claim.confidence >= 0.85:
            status = "verified"
            reason = "Claim matched independent bank evidence and passed all configured checks."
        else:
            status = "needs_review"
            reason = "; ".join(check.reason for check in report.checks if not check.passed) or "Independent second reading and confidence are required."
        slot = db.execute(
            "SELECT m.month FROM months m WHERE NOT EXISTS (SELECT 1 FROM payments p WHERE p.member_id=? AND p.month=m.month) ORDER BY m.month LIMIT 1",
            (sender,),
        ).fetchone()
        if slot is None:
            return {"bubbles": [
                {"type": "text", "text": "Screenshot received, but this member has no open demo instalment slot."},
                {"type": "result_card", "status": status, "amount_paise": claim.amount_paise, "utr": claim.utr, "reason": reason},
            ]}
        month = int(slot[0])
        amount = int(claim.amount_paise) if type(claim.amount_paise) is int and claim.amount_paise >= 0 else 0
        payment_status = "verified" if status == "verified" else "needs_review"
        with audited_transaction(db, context, actor=sender, reason=reason):
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO payments(id, member_id, month, amount_paise, utr, status) VALUES (?, ?, ?, ?, ?, ?)",
                (payment_id, sender, month, amount, claim.utr, payment_status),
            )
        if payment_status == "verified":
            post_verified_payment(db, context, payment_id, actor="system", reason=reason)
        _IMAGE_HASH_REGISTRY.record(image_hash)
        return {"bubbles": [
            {"type": "text", "text": "Screenshot received. Payment status is based on independent evidence and flagged claims stay out of the ledger."},
            {"type": "result_card", "status": status, "amount_paise": claim.amount_paise, "utr": claim.utr, "reason": reason},
        ]}
    except (OSError, ValueError, KeyError) as exc:
        return JSONResponse(status_code=422, content={"error": {"code": "message_processing_error", "message": str(exc)}})
    finally:
        db.close()


@app.post("/demo/load")
def demo_load(payload: DemoLoadRequest):
    if payload.actor != "foreman":
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Foreman required."}})
    db, context = connect(database_path())
    try:
        try:
            return load_demo(db, context, actor=payload.actor)
        except ValueError as exc:
            return JSONResponse(status_code=409, content={"error": {"code": "demo_load_conflict", "message": str(exc)}})
    finally:
        db.close()


@app.get("/state")
def state(role: str, member_id: str | None = None):
    db, _ = connect(database_path())
    try:
        try:
            return get_state(db, role=role, member_id=member_id)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": str(exc)}})
    finally:
        db.close()


# Independent pages on one development origin avoid unnecessary CORS setup.
app.mount("/chat", StaticFiles(directory=ROOT / "chat-ui", html=True), name="chat")
app.mount("/dashboard", StaticFiles(directory=ROOT / "dashboard", html=True), name="dashboard")
