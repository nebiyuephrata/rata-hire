# tests/test_courtroom.py
"""
Unit tests for the courtroom (investigators, arbiter, document critic),
the CV tailor, the Gemini client, and the PDF renderer.

All Gemini API calls are mocked — no real API key needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
from src.contracts.job_contract import CandidateProfileContract, ScrapedJobPosting

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles" / "ephrata"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def master_cv() -> MasterCVContract:
    data = json.loads((PROFILES_DIR / "master_cv_contract.json").read_text())
    return MasterCVContract.model_validate(data)


@pytest.fixture()
def candidate_profile() -> CandidateProfileContract:
    data = yaml.safe_load((PROFILES_DIR / "candidate_profile.yaml").read_text())
    return CandidateProfileContract.model_validate(data)


@pytest.fixture()
def sample_job() -> ScrapedJobPosting:
    return ScrapedJobPosting(
        source_id="test_source",
        company="TechCorp AI",
        role_title="Senior AI Engineer",
        location_raw="Remote — Worldwide",
        is_remote=True,
        salary_raw="$80,000 – $120,000",
        canonical_url="https://techcorp.ai/jobs/senior-ai-engineer",
        ats_type="greenhouse",
        description_text=(
            "We are looking for a Senior AI Engineer to build multi-agent systems "
            "using LangGraph and Python. You'll design evaluation harnesses, "
            "implement RAG pipelines, and work with FastAPI backends. "
            "Requirements: 3+ years Python, experience with LLMs, async programming. "
            "Nice to have: Kafka, distributed systems, MCP protocol. "
            "Remote-first company, open to contractors worldwide."
        ),
    )


@pytest.fixture()
def geo_pass_finding() -> InvestigatorFinding:
    return InvestigatorFinding(
        investigator_name="geo_eligibility",
        passed=True,
        score=90,
        reasoning="Remote-first, worldwide, no restrictions.",
        red_flags=[],
    )


@pytest.fixture()
def geo_fail_finding() -> InvestigatorFinding:
    return InvestigatorFinding(
        investigator_name="geo_eligibility",
        passed=False,
        score=10,
        reasoning="US Citizens Only, W2 required.",
        red_flags=["US Citizens Only", "W2 Only"],
    )


@pytest.fixture()
def stack_pass_finding() -> InvestigatorFinding:
    return InvestigatorFinding(
        investigator_name="stack_match",
        passed=True,
        score=85,
        reasoning="Strong overlap: Python, LangGraph, FastAPI, RAG.",
        red_flags=[],
    )


@pytest.fixture()
def legitimacy_pass_finding() -> InvestigatorFinding:
    return InvestigatorFinding(
        investigator_name="legitimacy_check",
        passed=True,
        score=92,
        reasoning="Legitimate company, clear JD, real role.",
        red_flags=[],
    )


@pytest.fixture()
def legitimacy_fail_finding() -> InvestigatorFinding:
    return InvestigatorFinding(
        investigator_name="legitimacy_check",
        passed=False,
        score=15,
        reasoning="Suspected crypto task scam, no real company.",
        red_flags=["crypto scam", "no company info"],
    )


@pytest.fixture()
def valid_payload(master_cv: MasterCVContract) -> TailoredCVPayload:
    """A valid payload referencing only real fact_ids from master."""
    return TailoredCVPayload(
        target_job_id="abc123",
        target_role_title="Senior AI Engineer",
        executive_summary="Experienced AI engineer with 5+ years building multi-agent systems.",
        prioritized_skill_categories=[
            {"name": "AI Agent Engineering", "skills": ["LangGraph", "MCP"]},
        ],
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
                        tailored_text="Selected top 3% globally for 720+ hr AI fellowship.",
                        matched_jd_keywords=["AI", "multi-agent"],
                    ),
                    TailoredBullet(
                        fact_id="EXP_TRP_B2",
                        tailored_text="Built multi-agent systems with LangGraph and MCP.",
                        matched_jd_keywords=["LangGraph", "multi-agent", "MCP"],
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
                        tailored_text="Built AI orchestration platform for multi-agent routing.",
                        matched_jd_keywords=["orchestration", "multi-agent"],
                    ),
                ],
            ),
        ],
        cover_letter_markdown="Dear Hiring Manager,\n\nI am excited to apply...",
    )


# ---------------------------------------------------------------------------
# Test: Arbiter deterministic hard-blockers (pure functions, no Gemini)
# ---------------------------------------------------------------------------
class TestArbiterDeterministicRules:
    """Test the arbiter's deterministic override logic WITHOUT hitting the LLM."""

    def test_geo_fail_forces_disqualification(self) -> None:
        from src.courtroom.arbiter import _deterministic_override

        findings = [
            InvestigatorFinding(
                investigator_name="geo_eligibility",
                passed=False,
                score=10,
                reasoning="US only.",
                red_flags=["US Only"],
            ),
            InvestigatorFinding(
                investigator_name="stack_match",
                passed=True,
                score=90,
                reasoning="Great match.",
            ),
            InvestigatorFinding(
                investigator_name="legitimacy_check",
                passed=True,
                score=95,
                reasoning="Legit.",
            ),
        ]
        force_fail, reason = _deterministic_override(findings)
        assert force_fail is True
        assert "geo_eligibility" in reason

    def test_legitimacy_fail_forces_disqualification(self) -> None:
        from src.courtroom.arbiter import _deterministic_override

        findings = [
            InvestigatorFinding(
                investigator_name="geo_eligibility",
                passed=True,
                score=85,
                reasoning="Remote OK.",
            ),
            InvestigatorFinding(
                investigator_name="stack_match",
                passed=True,
                score=80,
                reasoning="Good match.",
            ),
            InvestigatorFinding(
                investigator_name="legitimacy_check",
                passed=False,
                score=5,
                reasoning="Crypto scam.",
                red_flags=["crypto scam"],
            ),
        ]
        force_fail, reason = _deterministic_override(findings)
        assert force_fail is True
        assert "legitimacy_check" in reason

    def test_all_pass_no_override(self) -> None:
        from src.courtroom.arbiter import _deterministic_override

        findings = [
            InvestigatorFinding(
                investigator_name="geo_eligibility",
                passed=True,
                score=85,
                reasoning="OK.",
            ),
            InvestigatorFinding(
                investigator_name="stack_match",
                passed=True,
                score=80,
                reasoning="Good.",
            ),
            InvestigatorFinding(
                investigator_name="legitimacy_check",
                passed=True,
                score=90,
                reasoning="Legit.",
            ),
        ]
        force_fail, reason = _deterministic_override(findings)
        assert force_fail is False
        assert reason is None

    def test_weighted_score_calculation(self) -> None:
        from src.courtroom.arbiter import _weighted_score

        findings = [
            InvestigatorFinding(
                investigator_name="geo_eligibility",
                passed=True,
                score=80,
                reasoning="OK.",
            ),
            InvestigatorFinding(
                investigator_name="stack_match",
                passed=True,
                score=90,
                reasoning="Great.",
            ),
            InvestigatorFinding(
                investigator_name="legitimacy_check",
                passed=True,
                score=100,
                reasoning="Perfect.",
            ),
        ]
        # 80*0.30 + 90*0.50 + 100*0.20 = 24 + 45 + 20 = 89
        assert _weighted_score(findings) == 89


# ---------------------------------------------------------------------------
# Test: Arbiter with mocked Gemini (full async path)
# ---------------------------------------------------------------------------
class TestArbiterWithMockedGemini:
    """Test the arbiter's full flow with a mocked Gemini client."""

    @pytest.mark.asyncio
    async def test_arbiter_geo_fail_skips_llm(
        self,
        sample_job: ScrapedJobPosting,
        candidate_profile: CandidateProfileContract,
        geo_fail_finding: InvestigatorFinding,
        stack_pass_finding: InvestigatorFinding,
        legitimacy_pass_finding: InvestigatorFinding,
    ) -> None:
        """When geo fails, arbiter returns immediately without calling Gemini."""
        from src.courtroom import arbiter

        findings = [geo_fail_finding, stack_pass_finding, legitimacy_pass_finding]

        mock_generate = AsyncMock()
        with patch.object(arbiter, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            report = await arbiter.run_judicial_arbiter(
                sample_job, candidate_profile, findings
            )

            # Gemini should NOT have been called (hard-blocker fired)
            mock_generate.assert_not_called()

        assert report.qualified is False
        assert report.job_id == sample_job.job_id
        assert len(report.findings) == 3

    @pytest.mark.asyncio
    async def test_arbiter_legitimacy_fail_skips_llm(
        self,
        sample_job: ScrapedJobPosting,
        candidate_profile: CandidateProfileContract,
        geo_pass_finding: InvestigatorFinding,
        stack_pass_finding: InvestigatorFinding,
        legitimacy_fail_finding: InvestigatorFinding,
    ) -> None:
        from src.courtroom import arbiter

        findings = [geo_pass_finding, stack_pass_finding, legitimacy_fail_finding]

        mock_generate = AsyncMock()
        with patch.object(arbiter, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            report = await arbiter.run_judicial_arbiter(
                sample_job, candidate_profile, findings
            )
            mock_generate.assert_not_called()

        assert report.qualified is False

    @pytest.mark.asyncio
    async def test_arbiter_all_pass_calls_gemini(
        self,
        sample_job: ScrapedJobPosting,
        candidate_profile: CandidateProfileContract,
        geo_pass_finding: InvestigatorFinding,
        stack_pass_finding: InvestigatorFinding,
        legitimacy_pass_finding: InvestigatorFinding,
    ) -> None:
        """When all investigators pass, arbiter calls Gemini Pro for verdict."""
        from src.courtroom import arbiter

        findings = [geo_pass_finding, stack_pass_finding, legitimacy_pass_finding]

        mock_report = CourtroomAuditReport(
            job_id=sample_job.job_id,
            overall_score=88,
            qualified=True,
            findings=findings,
            tailoring_strategy_brief="Emphasise multi-agent and LangGraph expertise.",
            priority_keywords=["LangGraph", "Python", "multi-agent", "FastAPI"],
        )

        mock_generate = AsyncMock(return_value=mock_report)
        with patch.object(arbiter, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            report = await arbiter.run_judicial_arbiter(
                sample_job, candidate_profile, findings
            )
            mock_generate.assert_called_once()

        assert report.qualified is True
        assert report.overall_score == 88
        assert report.job_id == sample_job.job_id

    @pytest.mark.asyncio
    async def test_arbiter_enforces_threshold(
        self,
        sample_job: ScrapedJobPosting,
        candidate_profile: CandidateProfileContract,
        geo_pass_finding: InvestigatorFinding,
        stack_pass_finding: InvestigatorFinding,
        legitimacy_pass_finding: InvestigatorFinding,
    ) -> None:
        """Even if the LLM says qualified=True, if score < threshold, force False."""
        from src.courtroom import arbiter

        findings = [geo_pass_finding, stack_pass_finding, legitimacy_pass_finding]

        # LLM returns score=60, which is below threshold of 75
        mock_report = CourtroomAuditReport(
            job_id=sample_job.job_id,
            overall_score=60,
            qualified=True,  # LLM says yes, but score is too low
            findings=findings,
            tailoring_strategy_brief="Weak match.",
            priority_keywords=["Python"],
        )

        mock_generate = AsyncMock(return_value=mock_report)
        with patch.object(arbiter, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            report = await arbiter.run_judicial_arbiter(
                sample_job, candidate_profile, findings
            )

        # Deterministic threshold enforcement overrides LLM
        assert report.qualified is False
        assert report.overall_score == 60


# ---------------------------------------------------------------------------
# Test: Investigators with mocked Gemini
# ---------------------------------------------------------------------------
class TestInvestigatorsWithMockedGemini:
    """Test investigator functions return structured findings."""

    @pytest.mark.asyncio
    async def test_geo_investigator_returns_finding(
        self,
        sample_job: ScrapedJobPosting,
        candidate_profile: CandidateProfileContract,
        geo_pass_finding: InvestigatorFinding,
    ) -> None:
        from src.courtroom import investigators

        mock_generate = AsyncMock(return_value=geo_pass_finding)
        with patch.object(investigators, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            result = await investigators.investigate_geo_eligibility(
                sample_job, candidate_profile
            )

        assert result.investigator_name == "geo_eligibility"
        assert result.passed is True
        assert 0 <= result.score <= 100

    @pytest.mark.asyncio
    async def test_stack_investigator_returns_finding(
        self,
        sample_job: ScrapedJobPosting,
        candidate_profile: CandidateProfileContract,
        stack_pass_finding: InvestigatorFinding,
    ) -> None:
        from src.courtroom import investigators

        mock_generate = AsyncMock(return_value=stack_pass_finding)
        with patch.object(investigators, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            result = await investigators.investigate_stack_match(
                sample_job, candidate_profile, {"Python", "LangGraph", "FastAPI"}
            )

        assert result.investigator_name == "stack_match"
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_legitimacy_investigator_returns_finding(
        self,
        sample_job: ScrapedJobPosting,
        legitimacy_pass_finding: InvestigatorFinding,
    ) -> None:
        from src.courtroom import investigators

        mock_generate = AsyncMock(return_value=legitimacy_pass_finding)
        with patch.object(investigators, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            result = await investigators.investigate_legitimacy(sample_job)

        assert result.investigator_name == "legitimacy_check"
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_all_investigators_parallel(
        self,
        sample_job: ScrapedJobPosting,
        candidate_profile: CandidateProfileContract,
        geo_pass_finding: InvestigatorFinding,
        stack_pass_finding: InvestigatorFinding,
        legitimacy_pass_finding: InvestigatorFinding,
    ) -> None:
        from src.courtroom import investigators

        mock_generate = AsyncMock(
            side_effect=[
                geo_pass_finding,
                stack_pass_finding,
                legitimacy_pass_finding,
            ]
        )
        with patch.object(investigators, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            results = await investigators.run_all_investigators(
                sample_job,
                candidate_profile,
                {"Python", "LangGraph", "FastAPI"},
            )

        assert len(results) == 3
        names = {r.investigator_name for r in results}
        assert names == {"geo_eligibility", "stack_match", "legitimacy_check"}


# ---------------------------------------------------------------------------
# Test: Document Critic
# ---------------------------------------------------------------------------
class TestDocumentCritic:
    """Test the two-phase document audit."""

    @pytest.mark.asyncio
    async def test_valid_payload_passes_truth_check(
        self,
        valid_payload: TailoredCVPayload,
        master_cv: MasterCVContract,
        sample_job: ScrapedJobPosting,
    ) -> None:
        from src.courtroom import document_critic

        mock_critic_report = DocumentCriticReport(
            passed_truth_check=True,
            ats_rubric_score=88,
            violations=[],
            revision_instructions="",
        )

        mock_generate = AsyncMock(return_value=mock_critic_report)
        with patch.object(document_critic, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            report = await document_critic.audit_tailored_documents(
                valid_payload, master_cv, sample_job
            )

        assert report.passed_truth_check is True
        assert report.ats_rubric_score == 88
        assert len(report.violations) == 0

    @pytest.mark.asyncio
    async def test_invalid_payload_fails_truth_check(
        self,
        master_cv: MasterCVContract,
        sample_job: ScrapedJobPosting,
    ) -> None:
        """Payload with invented fact_id should fail deterministic truth check."""
        from src.courtroom import document_critic

        bad_payload = TailoredCVPayload(
            target_job_id="test123",
            target_role_title="Engineer",
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
                            fact_id="INVENTED_FAKE_B1",
                            tailored_text="Hallucinated.",
                            matched_jd_keywords=[],
                        ),
                    ],
                ),
            ],
        )

        # LLM returns whatever — deterministic check should override
        mock_critic_report = DocumentCriticReport(
            passed_truth_check=True,  # LLM wrongly says pass
            ats_rubric_score=50,
            violations=[],
            revision_instructions="Fix the fake fact.",
        )

        mock_generate = AsyncMock(return_value=mock_critic_report)
        with patch.object(document_critic, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            report = await document_critic.audit_tailored_documents(
                bad_payload, master_cv, sample_job
            )

        # Deterministic override: passed_truth_check must be False
        assert report.passed_truth_check is False
        assert any("INVENTED_FAKE_B1" in v for v in report.violations)


# ---------------------------------------------------------------------------
# Test: CV Tailor
# ---------------------------------------------------------------------------
class TestCVTailor:
    """Test the CV tailor with mocked Gemini responses."""

    @pytest.mark.asyncio
    async def test_valid_tailoring_succeeds(
        self,
        sample_job: ScrapedJobPosting,
        master_cv: MasterCVContract,
        valid_payload: TailoredCVPayload,
    ) -> None:
        from src.engine import cv_tailor

        audit_report = CourtroomAuditReport(
            job_id=sample_job.job_id,
            overall_score=88,
            qualified=True,
            findings=[
                InvestigatorFinding(
                    investigator_name="geo_eligibility",
                    passed=True,
                    score=90,
                    reasoning="OK.",
                ),
            ],
            tailoring_strategy_brief="Emphasise LangGraph.",
            priority_keywords=["LangGraph", "Python"],
        )

        mock_generate = AsyncMock(return_value=valid_payload)
        with patch.object(cv_tailor, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate
            result = await cv_tailor.tailor_cv_and_cover_letter(
                sample_job, master_cv, audit_report
            )

        assert result.target_job_id == sample_job.job_id
        assert len(result.experiences) > 0

    @pytest.mark.asyncio
    async def test_invalid_tailoring_raises_contract_violation(
        self,
        sample_job: ScrapedJobPosting,
        master_cv: MasterCVContract,
    ) -> None:
        """If the LLM invents a fact_id, the tailor must raise ContractViolationError."""
        from src.engine import cv_tailor

        bad_payload = TailoredCVPayload(
            target_job_id="test",
            target_role_title="Engineer",
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
                            fact_id="HALLUCINATED_FACT_999",
                            tailored_text="This was invented.",
                            matched_jd_keywords=[],
                        ),
                    ],
                ),
            ],
        )

        audit_report = CourtroomAuditReport(
            job_id=sample_job.job_id,
            overall_score=88,
            qualified=True,
            findings=[
                InvestigatorFinding(
                    investigator_name="geo_eligibility",
                    passed=True,
                    score=90,
                    reasoning="OK.",
                ),
            ],
            tailoring_strategy_brief="Go.",
            priority_keywords=["Python"],
        )

        mock_generate = AsyncMock(return_value=bad_payload)
        with patch.object(cv_tailor, "gemini", create=True) as mock_gemini:
            mock_gemini.generate_structured = mock_generate

            with pytest.raises(ContractViolationError) as exc_info:
                await cv_tailor.tailor_cv_and_cover_letter(
                    sample_job, master_cv, audit_report
                )

            assert "HALLUCINATED_FACT_999" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test: Gemini Client (unit-level)
# ---------------------------------------------------------------------------
class TestGeminiClient:
    """Test the GeminiClient wrapper with mocked internals."""

    @pytest.mark.asyncio
    async def test_generate_structured_returns_parsed_model(self) -> None:
        from src.engine.gemini_client import GeminiClient

        expected = InvestigatorFinding(
            investigator_name="geo_eligibility",
            passed=True,
            score=90,
            reasoning="All good.",
        )

        mock_response = MagicMock()
        mock_response.parsed = expected
        mock_response.text = expected.model_dump_json()

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        client = GeminiClient.__new__(GeminiClient)
        client._client = mock_client  # Inject mock directly

        result = await client.generate_structured(
            prompt="Test prompt",
            response_schema=InvestigatorFinding,
        )

        assert result.investigator_name == "geo_eligibility"
        assert result.passed is True
        assert result.score == 90

    @pytest.mark.asyncio
    async def test_generate_structured_raises_on_none(self) -> None:
        from src.engine.gemini_client import GeminiClient

        mock_response = MagicMock()
        mock_response.parsed = None
        mock_response.text = "unparseable garbage"

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        client = GeminiClient.__new__(GeminiClient)
        client._client = mock_client

        with pytest.raises(ValueError, match="unparseable"):
            await client.generate_structured(
                prompt="Bad prompt",
                response_schema=InvestigatorFinding,
            )

    def test_lazy_init_no_api_key_at_import(self) -> None:
        """Importing gemini_client should NOT require an API key."""
        from src.engine.gemini_client import GeminiClient

        client = GeminiClient()
        # _client should be None until first use
        assert client._client is None


# ---------------------------------------------------------------------------
# Test: PDF Renderer (HTML rendering only — no WeasyPrint PDF generation)
# ---------------------------------------------------------------------------
class TestPDFRenderer:
    """Test HTML template rendering without WeasyPrint (to avoid system deps)."""

    def test_cv_html_renders_without_error(
        self,
        valid_payload: TailoredCVPayload,
        master_cv: MasterCVContract,
    ) -> None:
        from src.engine.pdf_renderer import _render_cv_html

        html = _render_cv_html(valid_payload, master_cv)

        assert "Ephrata Nebiyu" in html
        assert "Senior AI Engineer" in html
        assert "Professional Summary" in html
        assert "EXP_TRP_B1" not in html  # fact_ids should NOT appear in output
        assert "Selected top 3%" in html  # tailored text SHOULD appear

    def test_cover_letter_html_renders_without_error(
        self,
        valid_payload: TailoredCVPayload,
        master_cv: MasterCVContract,
    ) -> None:
        from src.engine.pdf_renderer import _render_cover_letter_html

        html = _render_cover_letter_html(
            valid_payload, master_cv, company="TechCorp AI"
        )

        assert "Ephrata Nebiyu" in html
        assert "TechCorp AI" in html
        assert "Senior AI Engineer" in html
        assert "Dear Hiring Manager" in html  # from cover_letter_markdown

    def test_sanitise_filename(self) -> None:
        from src.engine.pdf_renderer import _sanitise_filename

        assert _sanitise_filename("hello world!@#") == "hello_world___"
        assert len(_sanitise_filename("a" * 100)) <= 50
