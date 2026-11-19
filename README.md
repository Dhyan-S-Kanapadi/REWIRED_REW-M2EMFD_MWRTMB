# ChitMirror

Screenshot in, verified ledger out. A four-person, six-hour hackathon project.
A payment screenshot is a claim; bank CSV evidence is required for verification.

## Run locally

Use Python 3.12 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn backend.main:app --reload
```

On macOS/Linux use `.venv/bin/python` in place of `.\.venv\Scripts\python`.
Open http://127.0.0.1:8000/chat/ and http://127.0.0.1:8000/dashboard/.
API docs: http://127.0.0.1:8000/docs. No Node build step is required.

Both pages call the backend directly. Set `CHITMIRROR_API_BASE` when starting
the frontend server to select the backend URL (empty means same origin).
The shared API contract and examples are in `contracts/`. A separate canned
stub is available for UI work; it does not perform payment verification.
Separate origins require backend CORS configuration.

## Stub API

Start the stub with `python -m uvicorn backend.stub:app --port 8001`.
Start the frontend server with `CHITMIRROR_API_BASE` set to the desired backend
URL (empty selects the same origin). For example, in PowerShell:

```powershell
$env:CHITMIRROR_API_BASE = "http://127.0.0.1:8001"
.\.venv\Scripts\python -m uvicorn backend.main:app --reload
```

The stub permits the local frontend origins on port 8000; set its
`CHITMIRROR_ALLOWED_ORIGINS` to a comma-separated list for other origins. For
canned message results, send `stub:verified`, `stub:duplicate`,
`stub:wrong_amount`, `stub:needs_review`, `stub:review_request`, or
`stub:reminder` in the multipart text field. Other messages return a text bubble.
Responses use the shared synthetic fixtures in `data/fixtures/`. The stub
does not persist state, actually send reminders, reset data, or verify screenshots.
The backend exposes `/health`, `/state`, `/message`, `/demo/load`, and `/reminders/send`; other business
endpoints remain separate work. The shared API contract is in `contracts/`.
Separate origins require backend CORS configuration.

The backend stores private demo reminder bubbles in SQLite (`data/chitmirror.db`
by default; set `CHITMIRROR_DATABASE` to override). While the server is running,
it checks once per minute in India time for payments due in two days, due today,
or overdue. The foreman `POST /reminders/send` trigger sends overdue reminders.
A recipient gets at most one reminder per month, stage and day; a verified and
posted payment is skipped. After the server is offline, only the currently
applicable stage is sent when it starts again; missed stages aren't replayed.
These are app bubbles, not real WhatsApp messages. `/state?role=member&member_id=...`
returns only the selected member's private bubbles; the demo selector is not
authentication, so this is not a security boundary against impersonation.
`POST /message` accepts a selected `sender` and returns that sender's dues,
statement and private reminders; it never accepts a target `member_id` in the
request, which keeps command replies member-scoped. The sender selector remains
a demo identity, not authentication.

The chat's statement reply uses the shared statement schema only: month,
instalment, dividend, late fee, prize and status. Dates, descriptions and
running balances are not present in that schema, so the UI does not invent them.
Reminder bubbles carry only `type` and `text` under the shared bubble schema;
available due information is written into the reminder text where present.

## Team folders

| Owner | Workspace |
| --- | --- |
| A | Reader and verification modules under `backend/`; tests under `tests/` |
| B | `backend/`: contract, services, storage, API and engine integration |
| C | `chat-ui/`: independent chat page; demo script and pitch |
| D | `dashboard/` and `data/`: independent dashboard, fixtures and scenario |

The original engine and diagram were not present in the repository. A replacement
pure settlement engine is provided in `backend/chit_engine.py`, and
`chitmirror_final.mermaid` documents the target architecture (some integrations
remain under development). Amounts are integer paise. The engine rejects fractional-paise
commission, instalments or dividends rather than silently rounding. Tags are
additional reconciliation amounts and their sum is reported separately; how
to account for or return tag surplus is an open product decision. No dividend
or payout is posted by settlement. If prized members are excluded, the caller
must supply prior winners; the current winner is also excluded. This policy and
the maximum discount require confirmation against the chit agreement.

`backend.ledger` posts a payment only after another service has independently
verified it and stored its status as `verified`; it does not verify evidence.
Statements read recorded ledger entries for one member. `instalment_paise` is
the actual posted payment including its paise tag (and any fee included in that
payment); dividend, fee and prize fields show separately recorded entries, not
automatic credits. Months without ledger entries are omitted. The caller must
enforce member access; demo sender selectors are not authentication. Existing
databases with duplicate payment postings must be reconciled before initializing
the new uniqueness indexes; no history is silently removed.

`backend.review.review_payment` records a foreman approve/reject decision on a
`needs_review` payment, using its payment ID as the demo review-item ID. An
approval is recorded as `manual_approved`, not bank-verified: it does not post
a verified payment or unlock payout. The review reason is captured in the audit
log. Review API routing and authentication are separate work; the `foreman`
actor string is a demo selector, not proof of identity.

`backend.late_fee` assesses bank credit timestamps against the end of the due
date in India time (UTC+05:30). The caller must supply the independently checked,
offset-aware bank credit time and the untagged base due; screenshot timestamps
are not inputs. Percentage fees use basis points of that base and reject
fractional paise. A nonzero fee may be recorded once only after a verified
payment is posted; its evidence timestamp and base are included in the audit
reason. The service trusts its caller to provide genuine bank evidence and does
not itself validate the bank CSV. A fee recorded after payment is a separate
ledger charge; collection and reconciliation of that charge remain future work.

`backend.payout` registers an immutable monthly settlement from the engine,
then records demo prize and dividend ledger entries only when every snapshotted
member has an exactly matching posted payment marked `verified`. Manual review
approval does not qualify. Duplicate calls do not add credits, and there is no
real transfer. Until fee collection and reconciliation exist, any nonzero late
fee blocks payout. The foreman selector and caller-supplied configuration are
demo inputs, not authenticated authorization; callers must ensure trusted group
settings and verified bank evidence. Existing duplicate prize/dividend ledger
entries must be reconciled before the database's new unique indexes can be
created. The extra tag amounts are tracked separately in the settlement;
their ultimate disposition remains an open product decision. Dividend ledger
entries record the allocation already deducted from the instalment; they are
not an additional cash payout or another deduction from the amount due.

## Tests

```powershell
.\.venv\Scripts\python -m pytest tests/test_app.py
.\.venv\Scripts\python -m playwright install chromium
```

With the development server running, in a second terminal:

```powershell
.\.venv\Scripts\python -m pytest tests/ui --base-url http://127.0.0.1:8000
```

CI runs backend checks and Chromium smoke tests. Manual checklist for UI PRs:
open both pages, confirm backend connection, inspect a phone-width chat and
projector-width dashboard, and confirm a stopped backend produces a readable error.

## Working agreement

One issue and branch per person (`T##-short-name`), maximum four issues in flight.
PRs reference `Closes #<issue>` and get a teammate review; keep main green.
Merge dependencies first unless the issue permits fixtures/stubs. Freeze at
hour 4:30; then only bug fixes. Follow the issue plan for business features.

Copy `.env.example` to `.env` when needed. Keys are blank by default. The
provider helper loads `.env` for local use; existing environment variables take
precedence. Do not commit credentials. Provider requests occur only when their
checks or the screenshot reader are invoked.

## T05 provider access smoke checks

The provider checks are separate CLI commands. They send one synthetic or
masked PNG/JPG payment screenshot, print an unverified field claim plus response
time, and fail if the call takes 10 seconds or more. They never write a payment,
call a bank or WhatsApp, or mark a screenshot `verified`.

Set `SARVAM_API_KEY` and `GROQ_API_KEY` in your local environment or the
local, ignored `.env`, then run:

```powershell
python -m scripts.smoke_sarvam --image .\path\to\synthetic-upi.png
python -m scripts.smoke_groq --image .\path\to\synthetic-upi.png
```

Sarvam uses its Document AI `POST /doc-ai/v1/job/parse` workflow, status polling,
and the documented ZIP download URL. Groq uses its vision chat completions API
with a base64 PNG/JPEG image. Groq replaces Claude at the user's request; check
hackathon sponsor requirements separately. Both commands report missing keys, quota/rate-limit
responses, malformed output, failed jobs and timeouts without printing secrets.
Live provider access is unconfirmed until these commands are run with valid keys
and a synthetic or masked screenshot. CI uses mocked HTTP only.


## Four-month synthetic demo

Start the backend with a fresh demo database, then load the four-month fixture from a foreman session:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/demo/load -ContentType "application/json" -Body '{"actor":"foreman"}'
python scripts/run_demo_scenarios.py
```

The loader seeds synthetic members, payment claims, independent bank evidence, and audit events. It never clears existing records; loading requires an empty demo database and subsequent loads are safe no-ops. The foreman dashboard also has a **Load demo** button. No real bank transfer is made.


## Screenshot verification setup
Set `SARVAM_API_KEY` and `ANTHROPIC_API_KEY` in your local environment (or an uncommitted `.env` file) to enable both readers. The shared-message screenshot flow compares extracted fields and checks the seeded bank evidence. If either provider is unavailable or readings disagree, the upload stays in the foreman review queue. The agreement score is not a calibrated probability.
