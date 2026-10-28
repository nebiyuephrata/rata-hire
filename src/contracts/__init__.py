# src/contracts — Pydantic V2 data contract layer for rata-hire
"""
Re-exports the primary contract models for convenient importing:

    from src.contracts import MasterCVContract, ScrapedJobPosting, ...
"""

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

__all__ = [
    # job_contract
    "ATSType",
    "ScrapedJobPosting",
    "CandidateProfileContract",
    # cv_contract
    "ContractViolationError",
    "MasterCVContract",
    "TailoredBullet",
    "TailoredCVPayload",
    "TailoredExperience",
    "TailoredProject",
    # audit_report
    "InvestigatorFinding",
    "CourtroomAuditReport",
    "DocumentCriticReport",
]
