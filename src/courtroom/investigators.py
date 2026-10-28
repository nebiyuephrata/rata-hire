# Parallel forensic checks: Geo/EMEA eligibility, Stack match, Legitimacy
"""
Three async investigator functions that run in parallel via ``asyncio.gather``
before the judicial arbiter synthesises a final verdict.

Each investigator returns an ``InvestigatorFinding`` produced by Gemini 2.5 Flash
with structured output enforcement.
"""

from __future__ import annotations

import asyncio
import logging

from config.settings import settings
from src.contracts.audit_report import InvestigatorFinding
from src.contracts.job_contract import CandidateProfileContract, ScrapedJobPosting
from src.engine.gemini_client import gemini

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Geo Eligibility Investigator
# ---------------------------------------------------------------------------
async def investigate_geo_eligibility(
    job: ScrapedJobPosting,
    profile: CandidateProfileContract,
) -> InvestigatorFinding:
    """
    Determine whether the role allows remote work from the candidate's
    location (Ethiopia / EMEA / UTC+3 / Global / B2B Contractor).

    Flags hard-blockers like "US Citizens Only", "W2 Only",
    "Security Clearance Required", or "EU Citizenship Required".
    """
    prompt = f"""You are a geo-eligibility investigator for a job application courtroom.

CANDIDATE PROFILE:
- Location: {profile.location.city}, {profile.location.country}
- Timezone: {profile.location.timezone}
- Accepted region tags: {', '.join(profile.location.region_tags)}
- Employment types: {', '.join(profile.preferences.employment_types)}
- Disallowed restrictions: {', '.join(profile.location.disallowed_restrictions)}

JOB POSTING:
- Company: {job.company}
- Role: {job.role_title}
- Location: {job.location_raw}
- Is Remote: {job.is_remote}
- Description excerpt (first 3000 chars):
{job.description_text[:3000]}

TASK:
1. Determine if this role allows the candidate to work from {profile.location.city}, {profile.location.country} (UTC+3).
2. Check if the job explicitly requires US citizenship, W2 employment, security clearance, or EU-only residency — these are hard blockers.
3. Check if the role is listed as "Remote", "Global", "EMEA", "Worldwide", "Anywhere", or mentions contractor/EOR eligibility.
4. Score 0-100 based on geo compatibility. 0 = hard-blocked, 100 = explicitly welcomes global remote.
5. Set passed=true ONLY if there are no hard geo blockers and the candidate can plausibly work from their location.
6. List any red flags detected.

Return your finding as a JSON object matching the InvestigatorFinding schema with investigator_name="geo_eligibility"."""

    return await gemini.generate_structured(
        prompt=prompt,
        response_schema=InvestigatorFinding,
        model=settings.gemini_fast_model,
        temperature=0.1,
    )


# ---------------------------------------------------------------------------
# Stack Match Investigator
# ---------------------------------------------------------------------------
async def investigate_stack_match(
    job: ScrapedJobPosting,
    profile: CandidateProfileContract,
    candidate_skills: set[str],
) -> InvestigatorFinding:
    """
    Score alignment between the JD requirements and the candidate's
    core stack (Python, FastAPI, LangGraph, MCP, LLM Eval, RAG,
    Kafka, Node.js, Distributed Systems, etc.).
    """
    prompt = f"""You are a stack-match investigator for a job application courtroom.

CANDIDATE SKILLS (from Master CV):
{', '.join(sorted(candidate_skills))}

CANDIDATE TARGET TITLES:
{', '.join(profile.preferences.target_titles)}

JOB POSTING:
- Company: {job.company}
- Role: {job.role_title}
- Description (first 4000 chars):
{job.description_text[:4000]}

TASK:
1. Extract all required and preferred technologies/skills from the job description.
2. Calculate overlap between JD requirements and candidate skills.
3. Score 0-100 based on skill alignment. Consider:
   - Core requirement matches (must-haves): weight heavily.
   - Nice-to-have matches: moderate weight.
   - Role title alignment with candidate target titles.
   - Years of experience alignment (candidate has 5+).
4. Set passed=true if score >= 50 (reasonable skill overlap).
5. List red flags like "requires 10+ years in a technology the candidate doesn't know".

Return your finding as a JSON object matching the InvestigatorFinding schema with investigator_name="stack_match"."""

    return await gemini.generate_structured(
        prompt=prompt,
        response_schema=InvestigatorFinding,
        model=settings.gemini_fast_model,
        temperature=0.1,
    )


# ---------------------------------------------------------------------------
# Legitimacy Investigator
# ---------------------------------------------------------------------------
async def investigate_legitimacy(
    job: ScrapedJobPosting,
) -> InvestigatorFinding:
    """
    Detect ghost jobs, unpaid trials, crypto/task scams,
    staffing spam, or suspicious postings.
    """
    prompt = f"""You are a legitimacy investigator for a job application courtroom.

JOB POSTING:
- Company: {job.company}
- Role: {job.role_title}
- Location: {job.location_raw}
- URL: {job.canonical_url}
- ATS Type: {job.ats_type.value}
- Salary: {job.salary_raw or 'Not disclosed'}
- Description (first 4000 chars):
{job.description_text[:4000]}

TASK:
1. Check for signs of a ghost job (posted indefinitely, unrealistic requirements, no real intent to hire).
2. Check for unpaid trial/test work disguised as part of the application process.
3. Check for crypto/blockchain task scams, MLM schemes, or "investment opportunity" disguised as jobs.
4. Check for staffing agency spam (vague descriptions, no real company, re-posted across many agencies).
5. Verify the posting has a real company name, specific role, and concrete responsibilities.
6. Score 0-100 for legitimacy. 100 = clearly legitimate, 0 = obvious scam.
7. Set passed=true if score >= 40 (benefit of the doubt for ambiguous postings).
8. List specific red flags detected.

Return your finding as a JSON object matching the InvestigatorFinding schema with investigator_name="legitimacy_check"."""

    return await gemini.generate_structured(
        prompt=prompt,
        response_schema=InvestigatorFinding,
        model=settings.gemini_fast_model,
        temperature=0.1,
    )


# ---------------------------------------------------------------------------
# Parallel runner
# ---------------------------------------------------------------------------
async def run_all_investigators(
    job: ScrapedJobPosting,
    profile: CandidateProfileContract,
    candidate_skills: set[str],
) -> list[InvestigatorFinding]:
    """
    Run all three investigators in parallel and return their findings.
    Order: [geo_eligibility, stack_match, legitimacy_check].
    """
    logger.info("Running 3 parallel investigators for job_id=%s", job.job_id)

    geo, stack, legitimacy = await asyncio.gather(
        investigate_geo_eligibility(job, profile),
        investigate_stack_match(job, profile, candidate_skills),
        investigate_legitimacy(job),
    )

    return [geo, stack, legitimacy]
