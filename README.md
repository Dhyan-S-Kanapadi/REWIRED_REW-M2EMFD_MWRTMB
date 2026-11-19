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

Both pages call the backend directly. Each owns its `config.js`; the static host
maps the single `CHITMIRROR_API_BASE` environment variable to
`window.CHITMIRROR_API_BASE` (empty means same origin). Point it at the
contract-compatible stub or real API to switch backends. The chat uses the
shared `GET /state` and `POST /message` contract. The checked-in backend
currently exposes only `/health`; the chat needs the T03 stub or real API.
Separate origins require backend CORS configuration.

## Team folders

| Owner | Workspace |
| --- | --- |
| A | Reader and verification modules under `backend/`; tests under `tests/` |
| B | `backend/`: contract, services, storage, API and engine integration |
| C | `chat-ui/`: independent chat page; demo script and pitch |
| D | `dashboard/` and `data/`: independent dashboard, fixtures and scenario |

The existing `chit_engine.py` and `chitmirror_final.mermaid` were not present in
the empty repository. Their owner should supply the originals; do not recreate
the completed engine or diagram. Integration belongs to T09.

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

Copy `.env.example` to `.env` when needed. Keys are blank and no provider calls
are made by this scaffold. Future services must load their environment explicitly;
the current app does not read `.env`.
