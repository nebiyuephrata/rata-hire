# Critic node auditing tailored CV/CL against JD and Master CV Contract
"""
Two-phase document audit:
  1. **Deterministic truth check**: ``payload.validate_against_master(master)``
  2. **LLM-based ATS rubric scoring**: Gemini 2.5 Flash evaluates keyword
     coverage, formatting quality, and professional tone.
"""

from __future__ import annotations

import logging

from config.settings import settings
from src.contracts.audit_report import DocumentCriticReport
from src.contracts.cv_contract import MasterCVContract, TailoredCVPayload
from src.contracts.job_contract import ScrapedJobPosting
from src.engine.gemini_client import gemini

logger = logging.getLogger(__name__)


async def audit_tailored_documents(
    payload: TailoredCVPayload,
    master: MasterCVContract,
    job: ScrapedJobPosting,
) -> DocumentCriticReport:
    """
    Audit a tailored CV/CL payload for truth-bound provenance compliance
    and ATS keyword coverage quality.

    Phase 1 (Deterministic):
        Run ``payload.validate_against_master(master)`` to check all
        ``fact_id``, ``exp_id``, and ``proj_id`` references.

    Phase 2 (LLM-based):
        Use Gemini 2.5 Flash to score ATS keyword coverage, formatting,
        and professional quality on a 0-100 rubric.

    Returns:
        A ``DocumentCriticReport`` with the combined results.
    """
    # ── Phase 1: Deterministic truth check ──
    deterministic_violations = payload.validate_against_master(master)
    passed_truth_check = len(deterministic_violations) == 0

    if deterministic_violations:
        logger.warning(
            "Document critic: %d deterministic violation(s) for job_id=%s",
            len(deterministic_violations),
            payload.target_job_id,
        )

    # ── Phase 2: LLM-based ATS rubric scoring ──
    payload_json = payload.model_dump_json(indent=2)

    prompt = f"""You are a document critic reviewing a tailored CV and cover letter for ATS optimisation quality.

JOB DESCRIPTION (first 4000 chars):
{job.description_text[:4000]}

TAILORED CV/CL PAYLOAD:
{payload_json[:6000]}

DETERMINISTIC TRUTH CHECK RESULTS:
- Passed: {passed_truth_check}
- Violations found: {len(deterministic_violations)}
{chr(10).join(f'  • {v}' for v in deterministic_violations) if deterministic_violations else '  • None'}

RUBRIC — Score each dimension 0-100, then compute a weighted average:
1. **Keyword Coverage (40%)**: Do the tailored bullets incorporate the JD's key technologies, skills, and domain terms?
2. **Quantification & Metrics (20%)**: Are concrete numbers, percentages, and scale metrics present in bullets?
3. **Role Relevance (20%)**: Are the selected experiences and projects the most relevant ones for this specific role?
4. **Professional Tone (10%)**: Is the language professional, concise, and free of fluff?
5. **Cover Letter Quality (10%)**: Does the cover letter reference specific JD requirements and company context?

TASK:
1. Compute the ats_rubric_score (0-100) as the weighted average of the 5 dimensions above.
2. Set passed_truth_check to {str(passed_truth_check).lower()}.
3. Include ALL deterministic violations in the violations list, plus any additional issues you detect (e.g. missing important JD keywords, generic language, inflated claims).
4. If the score is below 80 or there are violations, write specific revision_instructions for the CV tailor.
5. If everything is excellent, set revision_instructions to an empty string.

Return a JSON object matching the DocumentCriticReport schema."""

    report = await gemini.generate_structured(
        prompt=prompt,
        response_schema=DocumentCriticReport,
        model=settings.gemini_fast_model,
        temperature=0.1,
    )

    # Override truth check with deterministic result (don't trust LLM for this)
    report.passed_truth_check = passed_truth_check

    # Ensure deterministic violations are always included
    for v in deterministic_violations:
        if v not in report.violations:
            report.violations.insert(0, v)

    logger.info(
        "Document critic: job_id=%s truth_check=%s ats_score=%d violations=%d",
        payload.target_job_id,
        report.passed_truth_check,
        report.ats_rubric_score,
        len(report.violations),
    )

    return report
