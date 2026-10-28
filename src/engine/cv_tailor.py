# Truth-preserving CV and Cover Letter tailoring engine
"""
Uses Gemini 2.5 Pro to produce a ``TailoredCVPayload`` that strictly references
``fact_id``s from ``master_cv_contract.json``.

The tailor accepts optional ``user_feedback`` (from Telegram HITL) and
``revision_instructions`` (from the document critic) for iterative refinement.
"""

from __future__ import annotations

import json
import logging

from config.settings import settings
from src.contracts.audit_report import CourtroomAuditReport
from src.contracts.cv_contract import (
    ContractViolationError,
    MasterCVContract,
    TailoredCVPayload,
)
from src.contracts.job_contract import ScrapedJobPosting
from src.engine.gemini_client import gemini

logger = logging.getLogger(__name__)


async def tailor_cv_and_cover_letter(
    job: ScrapedJobPosting,
    master: MasterCVContract,
    audit_report: CourtroomAuditReport,
    *,
    user_feedback: str = "",
    revision_instructions: str = "",
) -> TailoredCVPayload:
    """
    Generate a tailored CV and cover letter for the given job posting.

    Args:
        job: The target job posting.
        master: The candidate's master CV contract (source of truth).
        audit_report: The courtroom audit report with strategy and keywords.
        user_feedback: Optional feedback from the Telegram HITL review.
        revision_instructions: Optional revision instructions from the critic.

    Returns:
        A ``TailoredCVPayload`` with all ``fact_id``s traced back to master.

    Raises:
        ContractViolationError: If the generated payload violates provenance.
    """
    # Serialise master CV data for the prompt
    master_json = master.model_dump_json(indent=2)

    feedback_section = ""
    if user_feedback:
        feedback_section += f"\n\nUSER FEEDBACK (from human reviewer):\n{user_feedback}"
    if revision_instructions:
        feedback_section += (
            f"\n\nREVISION INSTRUCTIONS (from document critic):\n{revision_instructions}"
        )

    prompt = f"""You are a truth-bound CV tailor for a job application system.

CRITICAL RULES:
1. You MUST ONLY use fact_ids, exp_ids, and proj_ids that exist in the Master CV Contract below.
2. You are STRICTLY FORBIDDEN from inventing skills, metrics, companies, dates, or bullet points.
3. Every tailored_text must be a truthful rephrasing of the original bullet — you may reorder words and add JD keywords, but you MUST preserve exact metrics and factual claims.
4. The executive_summary must be grounded in facts from the master CV.
5. The cover_letter_markdown must reference only real experiences and projects.

MASTER CV CONTRACT (source of truth):
{master_json}

TARGET JOB:
- Company: {job.company}
- Role: {job.role_title}
- Location: {job.location_raw}
- Description (first 5000 chars):
{job.description_text[:5000]}

COURTROOM STRATEGY:
- Tailoring strategy: {audit_report.tailoring_strategy_brief}
- Priority keywords to emphasise: {', '.join(audit_report.priority_keywords)}

{feedback_section}

TASK:
1. Write an executive_summary (3-4 sentences) tailored to this specific role, using only verifiable facts.
2. Select the most relevant experiences (2-4) and reorder/rephrase their bullets for ATS keyword alignment.
   - Each bullet's fact_id MUST match an existing fact_id from the master CV.
   - Each bullet's tailored_text should incorporate priority keywords naturally while preserving exact metrics.
   - List matched_jd_keywords for each bullet.
3. Select the most relevant projects (1-3) and tailor similarly.
4. Reorder prioritized_skill_categories to emphasise JD-relevant skills first.
5. Write a cover_letter_markdown (3-4 paragraphs) in Markdown format.
6. Set target_job_id to "{job.job_id}".
7. Set target_role_title to "{job.role_title}".

Return a JSON object matching the TailoredCVPayload schema."""

    payload = await gemini.generate_structured(
        prompt=prompt,
        response_schema=TailoredCVPayload,
        model=settings.gemini_pro_model,
        temperature=0.3,
    )

    # Enforce deterministic provenance validation
    violations = payload.validate_against_master(master)
    if violations:
        logger.error(
            "CV tailor produced %d violation(s) for job_id=%s:\n%s",
            len(violations),
            job.job_id,
            "\n".join(f"  • {v}" for v in violations),
        )
        raise ContractViolationError(violations)

    # Ensure job_id is correctly set (don't trust the LLM for this)
    payload.target_job_id = job.job_id
    payload.target_role_title = job.role_title

    logger.info(
        "CV tailor completed: job_id=%s, %d experiences, %d projects",
        job.job_id,
        len(payload.experiences),
        len(payload.projects),
    )

    return payload
