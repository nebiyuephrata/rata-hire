# Renders validated CV and Cover Letter contracts into ATS PDFs
"""
Uses Jinja2 for HTML templating and WeasyPrint for PDF generation.
Outputs go to ``settings.artifacts_dir / f"{job_id}_CV.pdf"`` and
``settings.artifacts_dir / f"{job_id}_CoverLetter.pdf"``.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

import jinja2
import markdown
import weasyprint

from config.settings import settings
from src.contracts.cv_contract import MasterCVContract, TailoredCVPayload

logger = logging.getLogger(__name__)

# Jinja2 environment loading templates from data/templates/
_JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(settings.templates_dir)),
    autoescape=jinja2.select_autoescape(["html"]),
)


def _render_cv_html(
    payload: TailoredCVPayload,
    master: MasterCVContract,
) -> str:
    """Render the tailored CV payload into an HTML string."""
    template = _JINJA_ENV.get_template("cv_template.html")

    return template.render(
        header=master.header.model_dump(),
        target_role_title=payload.target_role_title,
        executive_summary=payload.executive_summary,
        prioritized_skill_categories=payload.prioritized_skill_categories,
        experiences=[exp.model_dump() for exp in payload.experiences],
        projects=[proj.model_dump() for proj in payload.projects],
        education=master.education.model_dump(),
        certifications=[cert.model_dump() for cert in master.certifications],
    )


def _render_cover_letter_html(
    payload: TailoredCVPayload,
    master: MasterCVContract,
    company: str,
) -> str:
    """Render the cover letter into an HTML string."""
    template = _JINJA_ENV.get_template("cover_letter_template.html")

    # Convert cover letter markdown to HTML
    cover_letter_html = markdown.markdown(
        payload.cover_letter_markdown,
        extensions=["extra"],
    )

    return template.render(
        header=master.header.model_dump(),
        target_role_title=payload.target_role_title,
        company=company,
        date=datetime.now(UTC).strftime("%B %d, %Y"),
        cover_letter_html=cover_letter_html,
    )


def _html_to_pdf(html_content: str, output_path: Path) -> Path:
    """Convert an HTML string to a PDF file using WeasyPrint."""
    doc = weasyprint.HTML(string=html_content)
    doc.write_pdf(str(output_path))
    logger.info("PDF written: %s", output_path)
    return output_path


def _sanitise_filename(text: str) -> str:
    """Remove unsafe characters from a filename component."""
    return re.sub(r"[^\w\-]", "_", text)[:50]


async def render_pdfs(
    payload: TailoredCVPayload,
    master: MasterCVContract,
    company: str,
    job_id: str,
) -> tuple[Path, Path]:
    """
    Render the tailored CV and cover letter as ATS-compliant PDFs.

    Args:
        payload: The validated tailored CV/CL payload.
        master: The master CV contract (for header, education, certs).
        company: Company name (for cover letter addressee).
        job_id: The job_id used for output filenames.

    Returns:
        Tuple of (cv_pdf_path, cover_letter_pdf_path).
    """
    artifacts_dir = settings.artifacts_dir

    cv_filename = f"{job_id}_CV.pdf"
    cl_filename = f"{job_id}_CoverLetter.pdf"

    cv_path = artifacts_dir / cv_filename
    cl_path = artifacts_dir / cl_filename

    # Render HTML
    cv_html = _render_cv_html(payload, master)
    cl_html = _render_cover_letter_html(payload, master, company)

    # Convert to PDF
    _html_to_pdf(cv_html, cv_path)
    _html_to_pdf(cl_html, cl_path)

    logger.info(
        "PDFs rendered for job_id=%s: CV=%s, CL=%s",
        job_id,
        cv_path,
        cl_path,
    )

    return cv_path, cl_path
