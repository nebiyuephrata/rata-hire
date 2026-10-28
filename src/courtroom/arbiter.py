# Judicial arbitration node synthesizing final 0-100 score & tailoring brief
"""
The arbiter runs AFTER all three parallel investigators have submitted their
``InvestigatorFinding`` objects.  It synthesises a final ``CourtroomAuditReport``
using Gemini 2.5 Pro for deep reasoning.

Hard rules (deterministic, NOT delegated to the LLM):
  - If ``geo_eligibility.passed`` is False → force ``qualified = False``.
  - If ``legitimacy_check.passed`` is False → force ``qualified = False``.

If neither hard-blocker fires, the LLM computes a weighted score and outputs
a ``tailoring_strategy_brief`` + ``priority_keywords``.
"""

from __future__ import annotations

import logging

from config.settings import settings
from src.contracts.audit_report import CourtroomAuditReport, InvestigatorFinding
from src.contracts.job_contract import CandidateProfileContract, ScrapedJobPosting
from src.engine.gemini_client import gemini

logger = logging.getLogger(__name__)

# Weights for weighted-average fallback when no hard-blocker fires
_WEIGHTS = {
    "geo_eligibility": 0.30,
    "stack_match": 0.50,
    "legitimacy_check": 0.20,
}


def _deterministic_override(
    findings: list[InvestigatorFinding],
) -> tuple[bool, str | None]:
    """
    Apply deterministic hard-blocker rules BEFORE asking the LLM.

    Returns (should_force_fail, reason).
    """
    for f in findings:
        if f.investigator_name == "geo_eligibility" and not f.passed:
            return True, f"Hard-blocked by geo_eligibility: {f.reasoning}"
        if f.investigator_name == "legitimacy_check" and not f.passed:
            return True, f"Hard-blocked by legitimacy_check: {f.reasoning}"
    return False, None


def _weighted_score(findings: list[InvestigatorFinding]) -> int:
    """Compute weighted average score from investigator scores."""
    total = 0.0
    for f in findings:
        weight = _WEIGHTS.get(f.investigator_name, 0.0)
        total += f.score * weight
    return round(total)


async def run_judicial_arbiter(
    job: ScrapedJobPosting,
    profile: CandidateProfileContract,
    findings: list[InvestigatorFinding],
) -> CourtroomAuditReport:
    """
    Synthesise a final ``CourtroomAuditReport`` from investigator findings.

    1. Apply deterministic hard-blockers (geo / legitimacy).
    2. If no blocker, ask Gemini 2.5 Pro to compute a nuanced verdict
       with tailoring strategy and priority keywords.
    3. Enforce ``qualified`` based on ``min_courtroom_score_to_tailor``.
    """
    force_fail, fail_reason = _deterministic_override(findings)

    if force_fail:
        logger.warning(
            "Arbiter: hard-blocker fired for job_id=%s — %s",
            job.job_id,
            fail_reason,
        )
        return CourtroomAuditReport(
            job_id=job.job_id,
            overall_score=_weighted_score(findings),
            qualified=False,
            findings=findings,
            tailoring_strategy_brief=fail_reason or "",
            priority_keywords=[],
        )

    # No hard-blockers — ask Gemini Pro for nuanced analysis
    findings_text = "\n\n".join(
        f"### {f.investigator_name}\n"
        f"- Passed: {f.passed}\n"
        f"- Score: {f.score}/100\n"
        f"- Reasoning: {f.reasoning}\n"
        f"- Red flags: {', '.join(f.red_flags) if f.red_flags else 'None'}"
        for f in findings
    )

    prompt = f"""You are the Judicial Arbiter in a job application courtroom.
Your role is to synthesise a final qualification verdict from the 3 investigator reports below.

CANDIDATE:
- Name: {profile.full_name}
- Location: {profile.location.city}, {profile.location.country} ({profile.location.timezone})
- Target titles: {', '.join(profile.preferences.target_titles)}
- Min courtroom score to tailor: {profile.preferences.min_courtroom_score_to_tailor}

JOB:
- Company: {job.company}
- Role: {job.role_title}
- Location: {job.location_raw}
- Remote: {job.is_remote}

INVESTIGATOR REPORTS:
{findings_text}

TASK:
1. Compute an overall_score (0-100) as a weighted assessment:
   - Geo eligibility: 30% weight
   - Stack match: 50% weight
   - Legitimacy: 20% weight
2. Set qualified=true ONLY if overall_score >= {profile.preferences.min_courtroom_score_to_tailor}.
3. If qualified, write a concise tailoring_strategy_brief (2-3 sentences) advising the CV tailor how to best position the candidate.
4. If qualified, list 5-15 priority_keywords from the JD that the CV should emphasise.
5. Include all 3 investigator findings verbatim in your response.

Return a JSON object matching the CourtroomAuditReport schema."""

    report = await gemini.generate_structured(
        prompt=prompt,
        response_schema=CourtroomAuditReport,
        model=settings.gemini_pro_model,
        temperature=0.2,
    )

    # Enforce deterministic qualification threshold
    threshold = profile.preferences.min_courtroom_score_to_tailor
    if report.overall_score < threshold:
        report.qualified = False
        logger.info(
            "Arbiter: score %d < threshold %d — disqualified job_id=%s",
            report.overall_score,
            threshold,
            job.job_id,
        )

    # Ensure job_id and findings are correctly set
    report.job_id = job.job_id
    report.findings = findings

    logger.info(
        "Arbiter verdict: job_id=%s score=%d qualified=%s",
        job.job_id,
        report.overall_score,
        report.qualified,
    )

    return report
