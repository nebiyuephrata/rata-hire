# Truth-bound Pydantic V2 schemas & provenance validators for CV/CL
"""
Implements the truth-bound provenance contract per AGENTS.md §2.1:
  - Every tailored bullet MUST reference a valid ``fact_id`` from MasterCVContract.
  - ContractViolationError is raised when validation fails.
  - ``validate_against_master`` performs deterministic cross-reference checking.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------
class ContractViolationError(Exception):
    """Raised when the tailored CV violates the truth-bound provenance contract."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(
            f"ContractViolationError: {len(violations)} violation(s) detected.\n"
            + "\n".join(f"  • {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# Master CV Contract (source of truth)
# ---------------------------------------------------------------------------
class MasterBullet(BaseModel):
    """A single provenance-tracked bullet point."""
    fact_id: str
    text: str
    tags: list[str] = Field(default_factory=list)


class MasterExperience(BaseModel):
    """A work experience entry in the master CV."""
    exp_id: str
    company: str
    role: str
    period: str
    location: str
    bullets: list[MasterBullet]


class MasterProject(BaseModel):
    """A project entry in the master CV."""
    proj_id: str
    name: str
    technologies: list[str] = Field(default_factory=list)
    bullets: list[MasterBullet]


class MasterHeader(BaseModel):
    """Candidate header / contact info."""
    name: str
    default_title: str
    location: str
    phone: str
    email: str
    linkedin: str
    github: str


class MasterCoreFacts(BaseModel):
    """High-level career statistics."""
    years_of_experience: str
    max_user_scale: str
    trp_percentile: str
    trp_hours: str


class MasterSkillCategory(BaseModel):
    """A named grouping of skills."""
    category_id: str
    name: str
    skills: list[str]


class MasterEducation(BaseModel):
    """Education entry."""
    edu_id: str
    degree: str
    institution: str
    period: str


class MasterCertification(BaseModel):
    """Certification entry."""
    cert_id: str
    name: str
    issuer: str


class MasterCVContract(BaseModel):
    """
    Strict Pydantic V2 representation of ``master_cv_contract.json``.

    This is the **single source of truth** for the candidate's career data.
    The LLM is STRICTLY FORBIDDEN from inventing facts not present here.
    """

    schema_version: str
    candidate_id: str
    header: MasterHeader
    core_facts: MasterCoreFacts
    skill_categories: list[MasterSkillCategory]
    experiences: list[MasterExperience]
    projects: list[MasterProject]
    education: MasterEducation
    certifications: list[MasterCertification]

    # ---- Helper methods ----

    def get_all_fact_ids(self) -> set[str]:
        """Return every ``fact_id`` across experiences and projects."""
        ids: set[str] = set()
        for exp in self.experiences:
            for bullet in exp.bullets:
                ids.add(bullet.fact_id)
        for proj in self.projects:
            for bullet in proj.bullets:
                ids.add(bullet.fact_id)
        return ids

    def get_all_exp_ids(self) -> set[str]:
        """Return every ``exp_id``."""
        return {exp.exp_id for exp in self.experiences}

    def get_all_proj_ids(self) -> set[str]:
        """Return every ``proj_id``."""
        return {proj.proj_id for proj in self.projects}

    def get_all_skills(self) -> set[str]:
        """Return the union of all skills across every skill category."""
        skills: set[str] = set()
        for cat in self.skill_categories:
            skills.update(cat.skills)
        return skills


# ---------------------------------------------------------------------------
# Tailored CV models (output of CV Tailor)
# ---------------------------------------------------------------------------
class TailoredBullet(BaseModel):
    """
    A single ATS-optimised bullet.
    ``fact_id`` MUST exist in ``MasterCVContract.get_all_fact_ids()``.
    """
    fact_id: str = Field(
        ..., description="Must reference a valid fact_id from master_cv_contract.json."
    )
    tailored_text: str = Field(
        ...,
        min_length=1,
        description="ATS-keyword-aligned rephrasing preserving exact metrics and truth.",
    )
    matched_jd_keywords: list[str] = Field(
        default_factory=list,
        description="JD keywords this bullet was optimised for.",
    )


class TailoredExperience(BaseModel):
    """Tailored experience section."""
    exp_id: str
    company: str
    role: str
    period: str
    location: str
    bullets: list[TailoredBullet]


class TailoredProject(BaseModel):
    """Tailored project section."""
    proj_id: str
    name: str
    technologies: list[str]
    bullets: list[TailoredBullet]


class TailoredCVPayload(BaseModel):
    """
    Complete tailored CV/CL payload for a specific job posting.
    Every ``fact_id``, ``exp_id``, and ``proj_id`` inside MUST
    trace back to the ``MasterCVContract``.
    """

    target_job_id: str = Field(
        ..., description="SHA-256 job_id of the target ScrapedJobPosting."
    )
    target_role_title: str = Field(
        ..., description="Role title from the target job posting."
    )
    executive_summary: str = Field(
        ...,
        min_length=1,
        description="ATS-optimised professional summary paragraph.",
    )
    prioritized_skill_categories: list[dict] = Field(
        default_factory=list,
        description="Skill categories re-ordered/filtered for JD relevance.",
    )
    experiences: list[TailoredExperience] = Field(default_factory=list)
    projects: list[TailoredProject] = Field(default_factory=list)
    cover_letter_markdown: str = Field(
        default="",
        description="Markdown-formatted cover letter.",
    )

    def validate_against_master(self, master: MasterCVContract) -> list[str]:
        """
        Deterministic provenance validator.

        Returns a list of human-readable violation strings.  An empty list
        means the payload is contract-compliant.

        Checks performed:
          1. Every ``fact_id`` in tailored bullets exists in ``master``.
          2. Every ``exp_id`` exists in ``master``.
          3. Every ``proj_id`` exists in ``master``.
          4. Required contact / social links are present in the master header.
        """
        violations: list[str] = []

        valid_fact_ids = master.get_all_fact_ids()
        valid_exp_ids = master.get_all_exp_ids()
        valid_proj_ids = master.get_all_proj_ids()

        # --- Check experiences ---
        for exp in self.experiences:
            if exp.exp_id not in valid_exp_ids:
                violations.append(
                    f"exp_id '{exp.exp_id}' does not exist in MasterCVContract."
                )
            for bullet in exp.bullets:
                if bullet.fact_id not in valid_fact_ids:
                    violations.append(
                        f"fact_id '{bullet.fact_id}' (experience '{exp.exp_id}') "
                        f"does not exist in MasterCVContract."
                    )

        # --- Check projects ---
        for proj in self.projects:
            if proj.proj_id not in valid_proj_ids:
                violations.append(
                    f"proj_id '{proj.proj_id}' does not exist in MasterCVContract."
                )
            for bullet in proj.bullets:
                if bullet.fact_id not in valid_fact_ids:
                    violations.append(
                        f"fact_id '{bullet.fact_id}' (project '{proj.proj_id}') "
                        f"does not exist in MasterCVContract."
                    )

        # --- Check required contact / social links ---
        required_linkedin = "in/ephrata-nebiyu-9344b1205"
        required_github = "nebiyuephrata"

        if required_linkedin not in master.header.linkedin:
            violations.append(
                f"LinkedIn handle '{required_linkedin}' missing from master header "
                f"(found: '{master.header.linkedin}')."
            )
        if required_github not in master.header.github:
            violations.append(
                f"GitHub handle '{required_github}' missing from master header "
                f"(found: '{master.header.github}')."
            )

        return violations
