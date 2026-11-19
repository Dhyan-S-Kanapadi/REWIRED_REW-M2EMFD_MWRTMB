# ChitMirror demo materials

This folder contains the pitch deck, presenter script, dashboard screenshots,
workflow illustration, validation notes and rehearsal checklist. Demo records
and screenshots are synthetic. They must not be presented as real bank evidence.

## Project screenshots

The images below are previews of the independent Dashboard frontend using
synthetic four-month data. They show the UI and do not prove the complete
screenshot-verification flow works.

### Foreman view

![ChitMirror foreman dashboard with synthetic demo data](assets/dashboard-foreman.png)

### Member view

![ChitMirror member dashboard with synthetic statement and reminder](assets/dashboard-member.png)

## Local demo setup

From the repository root, point the backend at a fresh, dedicated demo database
before starting it. This keeps demo loading away from any other local database.

```powershell
New-Item -ItemType Directory -Force .demo | Out-Null
$env:CHITMIRROR_DATABASE = (Join-Path (Resolve-Path .demo) 't30-demo.db')
python -m uvicorn backend.main:app --reload
```

In another PowerShell window, load the synthetic fixture once:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/demo/load `
  -ContentType 'application/json' `
  -Body '{"actor":"foreman"}'
```

Open `http://127.0.0.1:8000/dashboard/` and switch to Member / Member 07 to
inspect the member statement and private reminder. The loader does not clear
existing records; use a fresh empty database if it reports a conflict.

Run the offline synthetic payment scenarios with:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python scripts/run_demo_scenarios.py
```

These five results come from the scenario runner and synthetic CSV, not the
Chat `/message` endpoint or a recorded end-to-end application flow.

## Current implementation boundaries

- `POST /reminders/send` creates private in-app reminder bubbles. It does not
  send WhatsApp messages.
- Late-fee and payout rules have backend service tests, but no live Chat/UI path
  is available for those actions.
- The screenshot reader returns `needs_review`. It does not verify payment or
  write a verified ledger entry.
- The Chat page and `/message` request format need integration work before the
  full screenshot-to-Dashboard flow can be rehearsed.
- Issue #24 is open and blocked on the integrated flow and real phone/projector
  verification. No full rehearsal recordings are claimed.

## Files

- [Five-minute demo script](CHITMIRROR_DEMO_SCRIPT.md)
- [Pitch deck](ChitMirror_Pitch_Deck.pptx)
- [Deck source](build_deck.ps1)
- [Validation notes](VALIDATION.md)
- [Rehearsal checklist](REHEARSAL_CHECKLIST.md)
- [Workflow illustration](assets/workflow.svg)
