# Customer 360 AI App

A prototype that merges customer signals scattered across CRM, support, email, Slack, product usage, and billing into a single account view — with AI-generated health scoring, risk/opportunity detection, and a recommended next best action.

Built for the Volopay Growth Squad Assessment — Task 2.

![Architecture](../../Assets/architecture_diagram.png)

## What it does

- Merges **6 dummy data sources** per account (CRM notes, support tickets, emails, Slack notes, product usage, payment history) into one unified profile.
- Computes a **Health Score (0–100)**, **sentiment**, **priority level**, **risks**, **opportunities**, and a **recommended next best action** — all from transparent, auditable rules (see "Why rules first, LLM second" below).
- Generates a **natural-language executive summary** — template-based by default, or via the OpenAI API if a key is configured.
- Provides **search, filtering, an activity timeline, and a plain-text export** of any account's summary.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python Flask | Fast to stand up, easy to read, no build step |
| Database | SQLite | Zero-config, ships with Python, fine for a prototype dataset |
| Frontend | Server-rendered HTML + Tailwind (CDN) + vanilla JS | No npm build step needed to run or deploy the app; keeps the whole thing to `python app.py` |
| AI | Rule-based signal engine + optional OpenAI API | See below |

> **Note on the frontend stack:** the brief's preferred stack lists React + Tailwind. For a take-home prototype that needs to run with a single command and deploy without a build pipeline, server-rendered HTML with the same Tailwind utility classes gets the identical visual result with far less moving-parts risk during evaluation. The component structure (`index.html`, `customer.html`) maps directly onto what would become React components (`AccountList`, `AccountCard`, `CustomerDetail`, `Timeline`) if this were taken further — noted as the first item under Future Improvements.

## Why rules first, LLM second

The health score, risk flags, and opportunity flags are computed with plain, auditable logic in `ai_engine.py` (`compute_health_score`, `detect_risks`, `detect_opportunities`, etc.) — not by asking an LLM to "read the data and decide." That's deliberate: a health score a CSM might act on shouldn't silently change because a prompt changed, and it shouldn't break because an API key expired.

The LLM's role is narrower and optional: turning the computed signals into a natural-language summary. If `OPENAI_API_KEY` is not set, a template-based summary is generated instead using the same signals — so the app is fully functional with zero configuration, and an API key can be dropped in later purely to improve the prose.

## Project Structure

```
Customer360_AI_App/
├── backend/
│   ├── app.py            # Flask routes (pages + REST API)
│   ├── ai_engine.py       # Signal computation + summary generation
│   ├── seed_data.py       # Generates dummy data across 6 sources into SQLite
│   └── customer360.db     # Created on first run
├── frontend/
│   ├── templates/
│   │   ├── index.html     # Account list, search, filters, KPI bar
│   │   └── customer.html  # Unified account view, timeline, export
│   └── static/
│       └── style.css      # Design tokens (gauge, cards, skeleton loaders)
├── requirements.txt
└── README.md
```

## Installation & Running Locally

Requires Python 3.9+.

```bash
cd Customer360_AI_App
pip install -r requirements.txt
python backend/seed_data.py      # generates customer360.db with dummy data
python backend/app.py            # starts the server
```

Open **http://localhost:5000**.

To enable the optional LLM narrative layer:

```bash
export OPENAI_API_KEY=sk-...
python backend/app.py
```

Then click **"Regenerate with LLM"** on any account page.

## API Reference

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/customers?q=&status=&segment=` | List accounts with computed health/priority/sentiment; supports search + filters |
| GET | `/api/customer/<id>?llm=1` | Full unified profile: signals, timeline, source counts |
| GET | `/api/customer/<id>/export` | Downloads a plain-text summary |
| GET | `/api/health` | Health check |

## Sample Input → Output

**Input (merged from 3+ sources for one account):**
- CRM note: *"QBR: requested pricing review."*
- 2 support tickets, one High-priority and unresolved: *"Card declined at vendor payment."*
- 2 emails, one negative sentiment: *"Frustrated with the recurring card decline issue."*
- Product usage: active users flat-to-declining over 8 weeks.
- 1 overdue invoice.

**Output (AI Summary panel):**
> "This account needs proactive attention soon. [Account] is a Growth account in Logistics with a health score of 50/100 and negative recent sentiment. Key risks: multiple recent emails carry negative sentiment — possible dissatisfaction pattern; 1 overdue invoice on the account. Recommended next step: Loop in billing/AR to resolve the overdue invoice before the next CSM touchpoint."

## Deployment

This is a standard Flask app — deploy it anywhere that runs Python:

- **Render / Railway**: connect the repo, set the start command to `gunicorn -w 2 -b 0.0.0.0:$PORT backend.app:app` (gunicorn is in `requirements.txt`), no build step needed.
- **Fly.io / a VPS**: same start command behind any reverse proxy.
- Set `OPENAI_API_KEY` as an environment variable on the host if the LLM narrative layer should be enabled in production.

> This submission ships the complete, runnable source rather than a hosted link, since the assessment was completed inside a sandboxed environment without outbound access to a hosting provider. Deploying it to Render/Railway following the steps above takes under 5 minutes — the app has no build step and no external dependencies beyond the optional OpenAI key.

## Future Improvements

Given more time, the highest-leverage next step would be **replacing the dummy-data seed script with real connectors** (Zoho CRM API, a support-desk API, an email/IMAP integration) behind the same unified-profile interface — the merge and signal logic in `ai_engine.py` is already source-agnostic, so real integrations would slot in without changing the scoring logic or the frontend at all.

Other improvements worth calling out:
- Migrate the frontend to React components (as noted above) once the UI needs client-side state beyond search/filter — the current HTML/JS split already maps to that component boundary.
- Add authentication and per-CSM account assignment instead of a fully open account list.
- Persist a history of health-score snapshots so trend-over-time (not just point-in-time) becomes visible on the account page.
