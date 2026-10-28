# tests/test_contracts.py
"""
Unit tests for the Pydantic V2 contract layer.

Tests cover:
  - MasterCVContract deserialization from master_cv_contract.json
  - Deterministic job_id hashing on ScrapedJobPosting
  - CandidateProfileContract YAML loading
  - TailoredCVPayload.validate_against_master — valid & invalid fact_ids
  - InvestigatorFinding / CourtroomAuditReport / DocumentCriticReport schemas
  - QA bank JSON schema validation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.contracts.audit_report import (
    CourtroomAuditReport,
    DocumentCriticReport,
    InvestigatorFinding,
)
from src.contracts.cv_contract import (
    ContractViolationError,
    MasterCVContract,
    TailoredBullet,
    TailoredCVPayload,
    TailoredExperience,
    TailoredProject,
)
from src.contracts.job_contract import (
    ATSType,
    CandidateProfileContract,
    ScrapedJobPosting,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles" / "ephrata"


@pytest.fixture()
def master_cv() -> MasterCVContract:
    """Load the real master_cv_contract.json and parse it."""
    data = json.loads((PROFILES_DIR / "master_cv_contract.json").read_text())
    return MasterCVContract.model_validate(data)


@pytest.fixture()
def candidate_profile() -> CandidateProfileContract:
    """Load the real candidate_profile.yaml and parse it."""
    data = yaml.safe_load((PROFILES_DIR / "candidate_profile.yaml").read_text())
    return CandidateProfileContract.model_validate(data)


# ---------------------------------------------------------------------------
# MasterCVContract
# ---------------------------------------------------------------------------
class TestMasterCVContract:
    """Tests for master CV deserialization and helpers."""

    def test_loads_from_json(self, master_cv: MasterCVContract) -> None:
        assert master_cv.candidate_id == "ephrata"
        assert master_cv.header.name == "Ephrata Nebiyu"
        assert master_cv.schema_version == "1.0.0"

    def test_get_all_fact_ids_returns_nonempty_set(
        self, master_cv: MasterCVContract
    ) -> None:
        fact_ids = master_cv.get_all_fact_ids()
        assert isinstance(fact_ids, set)
        assert len(fact_ids) > 0
        # Spot-check known fact_ids
        assert "EXP_TRP_B1" in fact_ids
        assert "PROJ_SF_B1" in fact_ids

    def test_get_all_skills_returns_nonempty_set(
        self, master_cv: MasterCVContract
    ) -> None:
        skills = master_cv.get_all_skills()
        assert isinstance(skills, set)
        assert "LangGraph" in skills
        assert "Python" in skills
        assert "FastAPI" in skills

    def test_get_all_exp_ids(self, master_cv: MasterCVContract) -> None:
        exp_ids = master_cv.get_all_exp_ids()
        assert "EXP_MERQ_2026" in exp_ids
        assert "EXP_10ACADEMY_2026" in exp_ids
        assert "EXP_ADDIS_2025" in exp_ids

    def test_get_all_proj_ids(self, master_cv: MasterCVContract) -> None:
        proj_ids = master_cv.get_all_proj_ids()
        assert "PROJ_SIGNALFORGE" in proj_ids
        assert "PROJ_DATA_AGENT" in proj_ids

    def test_education_parsed(self, master_cv: MasterCVContract) -> None:
        assert master_cv.education.edu_id == "EDU_AASTU"
        assert "Software Engineering" in master_cv.education.degree

    def test_certifications_parsed(self, master_cv: MasterCVContract) -> None:
        cert_ids = {c.cert_id for c in master_cv.certifications}
        assert "CERT_TRP_2026" in cert_ids


# ---------------------------------------------------------------------------
# ScrapedJobPosting
# ---------------------------------------------------------------------------
class TestScrapedJobPosting:
    """Tests for scraped job posting schemas."""

    def test_deterministic_job_id(self) -> None:
        """Same company+title+url always produces the same job_id."""
        posting_a = ScrapedJobPosting(
            source_id="test",
            company="Acme Corp",
            role_title="AI Engineer",
            location_raw="Remote",
            canonical_url="https://acme.com/jobs/123",
            description_text="Build AI systems.",
        )
        posting_b = ScrapedJobPosting(
            source_id="other_source",
            company="Acme Corp",
            role_title="AI Engineer",
            location_raw="San Francisco",
            canonical_url="https://acme.com/jobs/123",
            description_text="Different description.",
        )
        assert posting_a.job_id == posting_b.job_id

    def test_different_url_yields_different_id(self) -> None:
        posting_a = ScrapedJobPosting(
            source_id="test",
            company="Acme Corp",
            role_title="AI Engineer",
            location_raw="Remote",
            canonical_url="https://acme.com/jobs/123",
            description_text="Build AI systems.",
        )
        posting_b = ScrapedJobPosting(
            source_id="test",
            company="Acme Corp",
            role_title="AI Engineer",
            location_raw="Remote",
            canonical_url="https://acme.com/jobs/456",
            description_text="Build AI systems.",
        )
        assert posting_a.job_id != posting_b.job_id

    def test_ats_type_enum(self) -> None:
        posting = ScrapedJobPosting(
            source_id="test",
            company="TestCo",
            role_title="Eng",
            location_raw="Remote",
            canonical_url="https://boards.greenhouse.io/test/123",
            ats_type="greenhouse",
            description_text="A job.",
        )
        assert posting.ats_type == ATSType.GREENHOUSE

    def test_job_id_is_sha256_hex(self) -> None:
        posting = ScrapedJobPosting(
            source_id="test",
            company="TestCo",
            role_title="Eng",
            location_raw="Remote",
            canonical_url="https://example.com/1",
            description_text="Job desc.",
        )
        assert len(posting.job_id) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in posting.job_id)


# ---------------------------------------------------------------------------
# CandidateProfileContract
# ---------------------------------------------------------------------------
class TestCandidateProfileContract:
    """Tests for candidate profile deserialization."""

    def test_loads_from_yaml(self, candidate_profile: CandidateProfileContract) -> None:
        assert candidate_profile.profile_id == "ephrata"
        assert candidate_profile.full_name == "Ephrata Nebiyu"
        assert candidate_profile.location.timezone == "UTC+3"

    def test_preferences_parsed(
        self, candidate_profile: CandidateProfileContract
    ) -> None:
        prefs = candidate_profile.preferences
        assert prefs.min_salary_usd_annual == 60000
        assert prefs.min_courtroom_score_to_tailor == 75
        assert "AI Engineer" in prefs.target_titles


# ---------------------------------------------------------------------------
# TailoredCVPayload validation
# ---------------------------------------------------------------------------
class TestTailoredCVPayloadValidation:
    """Tests for truth-bound provenance validation."""

    def _build_valid_payload(self, master_cv: MasterCVContract) -> TailoredCVPayload:
        """Build a payload using ONLY valid fact_ids from the master."""
        return TailoredCVPayload(
            target_job_id="abc123",
            target_role_title="AI Engineer",
            executive_summary="Experienced AI engineer with 5+ years.",
            experiences=[
                TailoredExperience(
                    exp_id="EXP_10ACADEMY_2026",
                    company="Tenacious Intelligence Corporation (10 Academy)",
                    role="AI Agent & Evaluation Engineer",
                    period="Feb 2026 – May 2026",
                    location="Remote",
                    bullets=[
                        TailoredBullet(
                            fact_id="EXP_TRP_B1",
                            tailored_text="Selected top 3% globally for 720+ hr fellowship.",
                            matched_jd_keywords=["AI", "fellowship"],
                        ),
                    ],
                ),
            ],
            projects=[
                TailoredProject(
                    proj_id="PROJ_SIGNALFORGE",
                    name="SignalForge",
                    technologies=["Python", "FastAPI"],
                    bullets=[
                        TailoredBullet(
                            fact_id="PROJ_SF_B1",
                            tailored_text="Built deterministic AI orchestration platform.",
                            matched_jd_keywords=["orchestration"],
                        ),
                    ],
                ),
            ],
        )

    def test_valid_payload_has_no_violations(
        self, master_cv: MasterCVContract
    ) -> None:
        payload = self._build_valid_payload(master_cv)
        violations = payload.validate_against_master(master_cv)
        assert violations == []

    def test_invented_fact_id_fails_validation(
        self, master_cv: MasterCVContract
    ) -> None:
        """Core contract invariant: invented fact_ids MUST be caught."""
        payload = TailoredCVPayload(
            target_job_id="abc123",
            target_role_title="AI Engineer",
            executive_summary="Summary.",
            experiences=[
                TailoredExperience(
                    exp_id="EXP_10ACADEMY_2026",
                    company="10 Academy",
                    role="Engineer",
                    period="2026",
                    location="Remote",
                    bullets=[
                        TailoredBullet(
                            fact_id="INVENTED_FAKE_FACT_001",
                            tailored_text="This fact was hallucinated by the LLM.",
                            matched_jd_keywords=["fake"],
                        ),
                    ],
                ),
            ],
        )
        violations = payload.validate_against_master(master_cv)
        assert len(violations) >= 1
        assert any("INVENTED_FAKE_FACT_001" in v for v in violations)

    def test_invented_exp_id_fails_validation(
        self, master_cv: MasterCVContract
    ) -> None:
        payload = TailoredCVPayload(
            target_job_id="abc123",
            target_role_title="AI Engineer",
            executive_summary="Summary.",
            experiences=[
                TailoredExperience(
                    exp_id="EXP_FAKE_COMPANY_2026",
                    company="Fake Company",
                    role="Fake Role",
                    period="2026",
                    location="Nowhere",
                    bullets=[
                        TailoredBullet(
                            fact_id="EXP_TRP_B1",
                            tailored_text="Valid fact in fake company.",
                            matched_jd_keywords=[],
                        ),
                    ],
                ),
            ],
        )
        violations = payload.validate_against_master(master_cv)
        assert any("EXP_FAKE_COMPANY_2026" in v for v in violations)

    def test_invented_proj_id_fails_validation(
        self, master_cv: MasterCVContract
    ) -> None:
        payload = TailoredCVPayload(
            target_job_id="abc123",
            target_role_title="AI Engineer",
            executive_summary="Summary.",
            projects=[
                TailoredProject(
                    proj_id="PROJ_IMAGINARY",
                    name="Does Not Exist",
                    technologies=["Unobtainium"],
                    bullets=[
                        TailoredBullet(
                            fact_id="PROJ_SF_B1",
                            tailored_text="Valid fact in fake project.",
                            matched_jd_keywords=[],
                        ),
                    ],
                ),
            ],
        )
        violations = payload.validate_against_master(master_cv)
        assert any("PROJ_IMAGINARY" in v for v in violations)

    def test_multiple_violations_all_reported(
        self, master_cv: MasterCVContract
    ) -> None:
        """All violations should be collected, not just the first one."""
        payload = TailoredCVPayload(
            target_job_id="abc123",
            target_role_title="AI Engineer",
            executive_summary="Summary.",
            experiences=[
                TailoredExperience(
                    exp_id="EXP_NONEXISTENT",
                    company="Ghost Corp",
                    role="Ghost",
                    period="2099",
                    location="Mars",
                    bullets=[
                        TailoredBullet(
                            fact_id="GHOST_FACT_1",
                            tailored_text="Hallucinated.",
                            matched_jd_keywords=[],
                        ),
                        TailoredBullet(
                            fact_id="GHOST_FACT_2",
                            tailored_text="Also hallucinated.",
                            matched_jd_keywords=[],
                        ),
                    ],
                ),
            ],
        )
        violations = payload.validate_against_master(master_cv)
        # Should have at least 3: 1 exp_id + 2 fact_ids
        assert len(violations) >= 3

    def test_contract_violation_error_formatting(self) -> None:
        violations = ["fact_id 'X' not found", "exp_id 'Y' not found"]
        err = ContractViolationError(violations)
        assert "2 violation(s)" in str(err)
        assert err.violations == violations


# ---------------------------------------------------------------------------
# Audit Report schemas
# ---------------------------------------------------------------------------
class TestAuditReportSchemas:
    """Tests for courtroom audit and document critic report schemas."""

    def test_investigator_finding_valid(self) -> None:
        finding = InvestigatorFinding(
            investigator_name="geo_eligibility",
            passed=True,
            score=85,
            reasoning="Candidate is in UTC+3 with full EMEA overlap.",
            red_flags=[],
        )
        assert finding.passed is True
        assert finding.score == 85

    def test_investigator_score_bounds(self) -> None:
        with pytest.raises(Exception):
            InvestigatorFinding(
                investigator_name="stack_match",
                passed=True,
                score=150,  # Out of range
                reasoning="Invalid.",
            )

    def test_investigator_name_literal(self) -> None:
        with pytest.raises(Exception):
            InvestigatorFinding(
                investigator_name="nonexistent_investigator",  # type: ignore[arg-type]
                passed=False,
                score=0,
                reasoning="Invalid name.",
            )

    def test_courtroom_audit_report(self) -> None:
        report = CourtroomAuditReport(
            job_id="deadbeef" * 8,
            overall_score=82,
            qualified=True,
            findings=[
                InvestigatorFinding(
                    investigator_name="geo_eligibility",
                    passed=True,
                    score=90,
                    reasoning="Remote role, global candidates accepted.",
                ),
                InvestigatorFinding(
                    investigator_name="stack_match",
                    passed=True,
                    score=78,
                    reasoning="Strong overlap on LangGraph, Python, FastAPI.",
                ),
                InvestigatorFinding(
                    investigator_name="legitimacy_check",
                    passed=True,
                    score=80,
                    reasoning="Verified company, clear JD, no red flags.",
                ),
            ],
            tailoring_strategy_brief="Emphasise multi-agent orchestration.",
            priority_keywords=["LangGraph", "MCP", "AI Agent"],
        )
        assert report.qualified is True
        assert len(report.findings) == 3

    def test_document_critic_report(self) -> None:
        report = DocumentCriticReport(
            passed_truth_check=True,
            ats_rubric_score=92,
            violations=[],
            revision_instructions="",
        )
        assert report.passed_truth_check is True
        assert report.ats_rubric_score == 92

    def test_document_critic_with_violations(self) -> None:
        report = DocumentCriticReport(
            passed_truth_check=False,
            ats_rubric_score=45,
            violations=[
                "fact_id 'INVENTED_B1' not found in MasterCVContract.",
                "Metric '99% uptime' has no provenance.",
            ],
            revision_instructions="Remove invented bullet and re-run.",
        )
        assert report.passed_truth_check is False
        assert len(report.violations) == 2


# ---------------------------------------------------------------------------
# QA Bank
# ---------------------------------------------------------------------------
class TestQABank:
    """Tests for qa_bank.json schema integrity."""

    @pytest.fixture()
    def qa_bank(self) -> dict:
        data = json.loads((PROFILES_DIR / "qa_bank.json").read_text())
        return data

    def test_qa_bank_has_required_fields(self, qa_bank: dict) -> None:
        assert qa_bank["schema_version"] == "1.0.0"
        assert qa_bank["candidate_id"] == "ephrata"
        assert isinstance(qa_bank["fields"], list)
        assert len(qa_bank["fields"]) > 0

    def test_each_qa_field_has_structure(self, qa_bank: dict) -> None:
        for field in qa_bank["fields"]:
            assert "field_id" in field
            assert "question_patterns" in field
            assert "answer" in field
            assert "short_answer" in field
            assert isinstance(field["question_patterns"], list)
            assert len(field["question_patterns"]) > 0

    def test_qa_bank_covers_work_auth(self, qa_bank: dict) -> None:
        field_ids = {f["field_id"] for f in qa_bank["fields"]}
        assert "QA_WORK_AUTH" in field_ids

    def test_qa_bank_covers_timezone(self, qa_bank: dict) -> None:
        field_ids = {f["field_id"] for f in qa_bank["fields"]}
        assert "QA_TIMEZONE" in field_ids

    def test_qa_bank_covers_salary(self, qa_bank: dict) -> None:
        field_ids = {f["field_id"] for f in qa_bank["fields"]}
        assert "QA_SALARY_EXPECTATION" in field_ids

    def test_qa_bank_covers_links(self, qa_bank: dict) -> None:
        field_ids = {f["field_id"] for f in qa_bank["fields"]}
        assert "QA_LINKEDIN" in field_ids
        assert "QA_GITHUB" in field_ids
