# Pydantic V2 schemas for scraped job postings & candidate profile contract
"""
Defines the data contracts for:
  - ScrapedJobPosting: normalised representation of any job listing
  - CandidateProfileContract: mirrors profiles/{id}/candidate_profile.yaml
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# ATS type enum
# ---------------------------------------------------------------------------
class ATSType(str, Enum):
    """Known applicant-tracking-system types."""
    GREENHOUSE = "greenhouse"
    WORKABLE = "workable"
    LEVER = "lever"
    YC = "yc"
    GENERIC = "generic"


# ---------------------------------------------------------------------------
# ScrapedJobPosting
# ---------------------------------------------------------------------------
class ScrapedJobPosting(BaseModel):
    """
    Normalised representation of a scraped job listing.

    ``job_id`` is computed deterministically as SHA-256(lower(company) | lower(title) | canonical_url)
    so the same posting always maps to the same ID regardless of scrape timing.
    """

    source_id: str = Field(
        ..., description="Identifier of the scraping source (e.g. 'greenhouse_ai_jobs')."
    )
    company: str = Field(..., min_length=1, description="Hiring company name.")
    role_title: str = Field(..., min_length=1, description="Job title / role name.")
    location_raw: str = Field(
        ..., description="Raw location string as scraped (e.g. 'Remote — US/EMEA')."
    )
    is_remote: bool = Field(default=False, description="True if the role is fully remote.")
    salary_raw: str | None = Field(
        default=None, description="Raw salary/compensation string if present."
    )
    canonical_url: str = Field(
        ..., description="Canonical URL of the posting (used in job_id hash)."
    )
    ats_type: ATSType = Field(
        default=ATSType.GENERIC,
        description="Detected applicant-tracking-system type.",
    )
    description_text: str = Field(
        ..., min_length=1, description="Full job description as plain text."
    )
    scraped_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the posting was scraped.",
    )

    @computed_field  # type: ignore[misc]
    @property
    def job_id(self) -> str:
        """Deterministic SHA-256 hash of normalised company + title + canonical_url."""
        raw = f"{self.company.strip().lower()}|{self.role_title.strip().lower()}|{self.canonical_url.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CandidateProfileContract  (mirrors candidate_profile.yaml)
# ---------------------------------------------------------------------------
class CandidateLocation(BaseModel):
    """Candidate location metadata."""
    city: str
    country: str
    timezone: str
    region_tags: list[str] = Field(default_factory=list)
    disallowed_restrictions: list[str] = Field(default_factory=list)


class CandidatePreferences(BaseModel):
    """Candidate job-search preferences."""
    min_salary_usd_annual: int = Field(ge=0)
    min_hourly_rate_usd: int = Field(ge=0)
    min_courtroom_score_to_tailor: int = Field(ge=0, le=100)
    employment_types: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)


class CandidateProfileContract(BaseModel):
    """
    Strict Pydantic V2 representation of ``profiles/{id}/candidate_profile.yaml``.
    Never hardcode personal data in ``src/`` — always load dynamically via ``config.settings``.
    """

    profile_id: str
    full_name: str
    legal_name: str
    email: str
    phone: str
    location: CandidateLocation
    preferences: CandidatePreferences
