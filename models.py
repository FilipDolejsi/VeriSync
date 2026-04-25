from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ClassifierTag(str, Enum):
    style = "style"
    logic = "logic"
    security = "security"
    architecture = "architecture"
    test = "test"


class Severity(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class ReviewStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    complete = "complete"
    failed = "failed"
    merged = "merged"


# ── Core contracts ────────────────────────────────────────────────────────────

class User(BaseModel):
    id: str
    github_id: str
    username: str
    avatar_url: str
    wallet_id: str
    sat_balance: int = 0
    created_at: str
    last_login: str


class PRChunk(BaseModel):
    id: str
    pr_id: str
    file_path: str
    hunk_index: int
    language: str
    diff_text: str
    lines_changed: int
    classifier_tag: Optional[ClassifierTag] = None


class Finding(BaseModel):
    id: str
    chunk_id: str
    model_id: str
    severity: Severity
    category: str
    line_number: int
    description: str
    suggestion: str
    confidence: float = Field(ge=0.0, le=1.0)
    accepted: bool = False


class ReviewReport(BaseModel):
    pr_id: str
    pr_url: str
    status: ReviewStatus
    total_cost_sats: int
    findings: List[Finding] = Field(default_factory=list)
    passed_chunks: int = 0
    summary: str = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.critical)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.warning)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.info)


class Transaction(BaseModel):
    id: str
    user_id: str
    amount_sats: int
    direction: str  # "debit" | "credit"
    description: str
    timestamp: str
    pr_id: Optional[str] = None
    chunk_id: Optional[str] = None
    model_id: Optional[str] = None
