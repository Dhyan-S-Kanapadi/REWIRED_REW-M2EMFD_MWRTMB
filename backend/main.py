"""Development entry point; business endpoints belong to their own issues."""

import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
from pathlib import Path
import json
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from backend.database import connect
from backend.demo import load_demo
from backend.reminders import send_reminders
from backend.state import get_state

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
    actor: str = Field(min_length=1)


class DemoLoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1)


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
