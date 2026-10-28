# rata-hire

Autonomous AI Job Discovery, Judicial Qualification, Truth-Bound CV Tailoring, Telegram HITL Approval, and Playwright Form Submission Engine.

## Architecture Overview

`rata-hire` combines three proven systems engineering patterns:
1. **Spec-Driven MCP & Profile Isolation (`project-chimera`)**: Decouples user profiles (`profiles/{user}/`) and browser workspaces from core orchestration.
2. **Digital Courtroom Qualification (`automaton-auditor`)**: Evaluates scraped jobs in parallel across Geo/EMEA eligibility, Tech Stack alignment, and Scam/Ghost-Job risk before a Chief Arbiter scores the role (0–100).
3. **Truth-Contract Governance (`data-contract-enforcer`)**: Every tailored CV bullet and skill is cryptographically/structurally bound to `fact_id` entries in `master_cv_contract.json`, guaranteeing zero LLM hallucinations and 100% ATS compliance.

## End-to-End Workflow
1. **Discovery (24h Cron / Trigger)**: Scrapes prioritized Tier-1/Tier-2 remote job boards (HiringCafe, Himalayas, YC Work at a Startup, Wellfound, Workable, EU Remote Jobs).
2. **Courtroom Triage**: Filters out US-only or low-match roles; roles scoring `>= 75/100` advance.
3. **Truth-Bound Tailoring**: Gemini 2.5 Pro selects optimal bullet variations, orders ATS keywords, adjusts the Executive Summary, and writes a custom Cover Letter.
4. **Contract Enforcer & Document Critic**: Verifies 0 fabricated facts and compiles single-column ATS PDFs (`CV.pdf` + `CoverLetter.pdf`).
5. **Telegram HITL Pause (`interrupt()`)**: Sends the Audit Report + PDFs to your Telegram with `[✅ Approve & Apply]`, `[🔄 Reiterate]`, and `[❌ Skip]` buttons.
6. **Playwright Submission**: Upon approval, fills the ATS form (Greenhouse, Workable, Lever), attaches the PDFs, and logs the submission.

## Quickstart

```bash
# 1. Create virtual environment & install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# 2. Configure environment variables
cp .env.example .env
# Edit .env with GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, and TELEGRAM_CHAT_ID

# 3. Run the agent
python -m src.main