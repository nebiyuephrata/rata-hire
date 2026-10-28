# Rubric scoring and contract violation report schemas
"""
Defines the data contracts for:
  - InvestigatorFinding: result of one forensic investigator
  - CourtroomAuditReport: aggregated courtroom qualification decision
  - DocumentCriticReport: truth-check & ATS rubric scoring for tailored CV
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Investigator Finding
# ---------------------------------------------------------------------------
class InvestigatorFinding(BaseModel):
    """
    Output of a single courtroom investigator.

    Investigators run in parallel before the arbiter renders a verdict.
    """

    investigator_name: Literal["geo_eligibility", "stack_match", "legitimacy_check"] = Field(
        ..., description="Which investigator produced this finding."
    )
    passed: bool = Field(
        ..., description="Whether the investigation passed."
    )
    score: int = Field(
        ..., ge=0, le=100, description="Confidence score (0-100)."
    )
    reasoning: str = Field(
        ..., min_length=1, description="Human-readable reasoning for the verdict."
    )
    red_flags: list[str] = Field(
        default_factory=list, description="Specific red flags detected (if any)."
    )


# ---------------------------------------------------------------------------
# Courtroom Audit Report
# ---------------------------------------------------------------------------
class CourtroomAuditReport(BaseModel):
    """
    Aggregated qualification report produced by the courtroom arbiter
    after all three investigators have submitted their findings.

    If ``qualified`` is False, no CV-tailoring tokens should be spent.
    """

    job_id: str = Field(
        ..., description="SHA-256 job_id of the evaluated posting."
    )
    overall_score: int = Field(
        ..., ge=0, le=100, description="Weighted overall qualification score (0-100)."
    )
    qualified: bool = Field(
        ...,
        description=(
            "True if the job passes the courtroom bar "
            "(overall_score >= candidate min_courtroom_score_to_tailor)."
        ),
    )
    findings: list[InvestigatorFinding] = Field(
        ...,
        min_length=1,
        description="One finding per investigator (geo, stack, legitimacy).",
    )
    tailoring_strategy_brief: str = Field(
        default="",
        description="Short strategy note for the CV tailor if qualified.",
    )
    priority_keywords: list[str] = Field(
        default_factory=list,
        description="JD keywords the CV tailor should prioritise.",
    )


# ---------------------------------------------------------------------------
# Document Critic Report
# ---------------------------------------------------------------------------
class DocumentCriticReport(BaseModel):
    """
    Output of the document critic that reviews a tailored CV/CL payload
    for truth-bound provenance compliance and ATS optimisation quality.
    """

    passed_truth_check: bool = Field(
        ...,
        description="True if every fact_id traces back to the MasterCVContract.",
    )
    ats_rubric_score: int = Field(
        ..., ge=0, le=100, description="ATS optimisation rubric score (0-100)."
    )
    violations: list[str] = Field(
        default_factory=list,
        description="List of truth-bound contract violations detected.",
    )
    revision_instructions: str = Field(
        default="",
        description="Instructions for the CV tailor if revision is needed.",
    )
