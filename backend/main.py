"""Development entry point; business endpoints belong to their own issues."""

import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
from pathlib import Path
import json

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.datastructures import UploadFile

from backend.database import connect
from backend.messages import handle_message
from backend.demo import load_demo
from backend.reminders import send_reminders
from backend.state import get_state
from backend.review import review_payment
from backend.simulated_demo import FIXTURES, submit_simulated
from backend.provider_smoke import ProviderSmokeError
from backend.screenshot_reader import needs_review_response, read_uploaded_screenshot
import httpx

ROOT = Path(__file__).resolve().parent.parent
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


class DemoLoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str
    item_id: str
    decision: str
    reason: str


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Invalid request."}})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/demo/screenshot")
def demo_screenshot(scenario: str = "missing"):
    if os.environ.get("CHITMIRROR_SIMULATED_DEMO") != "1":
        return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Demo screenshot unavailable."}})
    samples = {"missing": "fake/gpay/t07-fake-gpay-001.png", "matching": "genuine/gpay/t07-genuine-gpay-001.png", "mismatch": "wrong_amount/gpay/t07-wrong-amount-gpay-001.png"}
    if scenario not in samples:
        return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Demo scenario unavailable."}})
    return FileResponse(FIXTURES / samples[scenario], media_type="image/png")


@app.get("/config.js")
def frontend_config():
    api_base = os.environ.get("CHITMIRROR_API_BASE", "")
    simulated = os.environ.get("CHITMIRROR_SIMULATED_DEMO") == "1"
    return Response(f"window.CHITMIRROR_API_BASE = {json.dumps(api_base)}; window.CHITMIRROR_SIMULATED_DEMO = {json.dumps(simulated)}; window.CHITMIRROR_DEMO_SCENARIOS = {json.dumps(simulated)};", media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.post("/reminders/send")
def reminders_send(payload: ReminderRequest):
    if payload.actor != "foreman":
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Foreman required."}})
    db, context = connect(database_path())
    try:
        return {"sent": send_reminders(db, context, actor=payload.actor, send_now=True)}
    finally:
        db.close()


@app.post("/message")
async def message(request: Request):
    """Route member text commands and screenshots through one endpoint."""
    image = None
    try:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type == "application/json":
            payload = MessageRequest.model_validate(await request.json())
        elif content_type in {"multipart/form-data", "application/x-www-form-urlencoded"}:
            form = await request.form()
            if set(form.keys()) - {"sender", "text", "image"}:
                raise ValueError("Unexpected form field")
            image = form.get("image")
            if image is not None and not isinstance(image, UploadFile):
                raise ValueError("Invalid image")
            payload = MessageRequest.model_validate({"sender": form.get("sender"), "text": form.get("text", "")})
        else:
            raise ValueError("Unsupported content type")
    except (ValueError, ValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Invalid message request."}})
    sender, text = payload.sender.strip(), payload.text.strip()
    if not sender.strip() or (not text.strip() and image is None):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Sender and text or image are required."}})
    if image is None:
        db, _ = connect(database_path())
        try:
            try:
                return handle_message(db, sender=sender, text=text)
            except ValueError as exc:
                return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": str(exc)}})
        finally:
            db.close()
    try:
        content = await image.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise ProviderSmokeError("Screenshot exceeds 10 MiB.")
        if os.environ.get("CHITMIRROR_SIMULATED_DEMO") == "1":
            db, context = connect(database_path())
            try:
                try:
                    return submit_simulated(db, context, sender=sender, content=content)
                except ValueError as exc:
                    return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": str(exc)}})
            finally:
                db.close()
        with httpx.Client() as client:
            claim = await asyncio.to_thread(read_uploaded_screenshot, image.filename or "screenshot", content, client)
        return needs_review_response(claim)
    except ProviderSmokeError as exc:
        return JSONResponse(status_code=422, content={"error": {"code": "screenshot_reader_error", "message": str(exc)}})


@app.post("/review")
def review(payload: ReviewRequest):
    db, context = connect(database_path())
    try:
        try:
            return review_payment(db, context, **payload.model_dump())
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": str(exc)}})
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
