"""Two-reader screenshot extraction; claims are never proof of payment."""

from __future__ import annotations

import tempfile
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import httpx

from backend.provider_smoke import ExtractionClaim, ProviderSmokeError, run_claude_smoke, run_sarvam_smoke


@dataclass(frozen=True)
class ScreenshotClaim:
    """Untrusted values only. None means the value was not visibly available."""

    utr: str | None
    amount_paise: int | None
    payee: str | None
    transaction_status: str | None
    transaction_date: str | None
    transaction_time: str | None
    payment_application: str | None
    confidence: float | None
    readers_agree: bool | None = None

    @classmethod
    def from_extraction(cls, extraction: ExtractionClaim) -> "ScreenshotClaim":
        return cls(extraction.utr, extraction.amount_paise, extraction.payee,
                   extraction.transaction_status, extraction.transaction_date,
                   extraction.transaction_time, extraction.payment_application, None, None)

    @classmethod
    def from_two_readers(cls, first: ExtractionClaim, second: ExtractionClaim) -> "ScreenshotClaim":
        fields = ("utr", "amount_paise", "payee", "transaction_status",
                  "transaction_date", "transaction_time", "payment_application")
        values = []
        comparable = []
        for field in fields:
            left, right = getattr(first, field), getattr(second, field)
            values.append(left)
            if left is not None or right is not None:
                comparable.append((left, right))
        matches = sum(left is not None and right is not None and left == right for left, right in comparable)
        confidence = matches / len(comparable) if comparable else 0.0
        return cls(*values, confidence, all(left == right for left, right in comparable))


class ScreenshotReaderQueue:
    """Small bounded worker boundary for multiple local uploads; no external queue exists."""

    def __init__(self, workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="payment-reader")

    def submit(self, image_path: Path, client: httpx.Client) -> Future[ScreenshotClaim]:
        return self._executor.submit(read_screenshot, image_path, client)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)


def read_screenshot(image_path: Path, client: httpx.Client) -> ScreenshotClaim:
    """Read with Sarvam and Claude; any missing or disagreeing second read stays review-only."""
    first = run_sarvam_smoke(image_path, client=client)
    try:
        second = run_claude_smoke(image_path, client=client)
    except ProviderSmokeError:
        return ScreenshotClaim.from_extraction(first)
    return ScreenshotClaim.from_two_readers(first, second)


def read_uploaded_screenshot(filename: str, content: bytes, client: httpx.Client) -> ScreenshotClaim:
    """Validate and process one upload without retaining the image on disk."""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise ProviderSmokeError("Only PNG and JPG/JPEG screenshots are supported.")
    with tempfile.TemporaryDirectory(prefix="chitmirror-reader-") as directory:
        image_path = Path(directory) / f"screenshot{suffix}"
        image_path.write_bytes(content)
        return read_screenshot(image_path, client)


def needs_review_response(claim: ScreenshotClaim) -> dict:
    """The only public contract mapping for OCR: a screenshot remains a claim."""
    return {"bubbles": [
        {"type": "text", "text": "Payment screenshot received for independent review."},
        {"type": "result_card", "status": "needs_review", "amount_paise": claim.amount_paise,
         "utr": claim.utr, "reason": "Screenshot extraction is a claim; independent bank evidence is required."},
    ]}
