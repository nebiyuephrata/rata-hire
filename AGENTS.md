# AGENTS.md — Coding Agent Operational Contract for `rata-hire`

## 1. Project Identity & Core Objective
`rata-hire` is a local, profile-isolated autonomous AI Job Discovery, Judicial Qualification, Truth-Bound CV Tailoring, Telegram Human-in-the-Loop (HITL), and Playwright MCP Form Submission agent.

## 2. Non-Negotiable Architectural Invariants
1. **Truth-Bound Provenance (`src/contracts/cv_contract.py`)**:
   - The LLM is STRICTLY FORBIDDEN from inventing skills, metrics, companies, or dates.
   - Every tailored bullet point or skill emitted by the CV Tailor MUST reference a valid `fact_id` from `profiles/{active_profile}/master_cv_contract.json`.
   - Any unverified claim must raise a `ContractViolationError` and trigger a critic retry.
2. **Multi-User Profile Isolation (`profiles/{profile_id}/`)**:
   - Never hardcode personal candidate data, emails, phone numbers, or file paths inside `src/`.
   - Always resolve candidate data dynamically via `config.settings.settings` (`settings.master_cv_path`, `settings.candidate_profile_path`, `settings.qa_bank_path`).
3. **Human-in-the-Loop Gate (`src/workflows/application_graph.py`)**:
   - The agent must NEVER submit an application without hitting the `telegram_review_node` (`langgraph.types.interrupt`).
   - Only `Command(resume={"action": "approve"})` from the Telegram handler can unlock the Playwright submission node.
4. **Digital Courtroom Qualification (`src/courtroom/`)**:
   - Job qualification runs 3 parallel forensic investigators (`geo_eligibility`, `stack_match`, `legitimacy_check`) followed by a deterministic `arbiter` node before any CV tailoring tokens are spent.

## 3. Tech Stack & Library Standards
- **Python**: `>=3.10`, strict type hints (`typing`, `TypedDict`, `Annotated`), `async`/`await` throughout IO nodes.
- **LLM SDK**: Use `google-genai` (`from google import genai`), NOT the legacy `google-generativeai` package.
  - Fast extraction/investigators: `gemini-2.5-flash`
  - Deep reasoning, arbiter, CV tailoring: `gemini-2.5-pro`
  - Enforce structured outputs via `response_mime_type="application/json"` and `response_schema=PydanticModel`.
- **Data Validation**: Pydantic V2 (`BaseModel`, `Field`, `field_validator`, `model_validator`).
- **Orchestration**: `langgraph` (`StateGraph`, `START`, `END`, `interrupt`, `Command`, `SqliteSaver`).
- **Telegram**: `aiogram` v3.x (async routers, `InlineKeyboardMarkup`, callback query handlers).
- **Browser Automation**: Playwright async API (`playwright.async_api`) or `@playwright/mcp`.

## 4. Coding Conventions
- Keep files modular and focused on a single responsibility.
- Never catch generic `Exception` silently; log structured context and update workflow state cleanly.
- Write unit tests in `tests/` using `pytest` and `pytest-asyncio` before marking a module complete.