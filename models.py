from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Any

from pydantic import BaseModel


class ModelEntry(BaseModel):
    id: str
    name: str
    provider: Literal["ollama", "anthropic"]
    cost_sats: int
    endpoint_url: str
    capability_tags: List[str]


class User(BaseModel):
    id: str
    github_id: str
    username: str
    avatar_url: str
    wallet_id: str
    sat_balance: int = 0


class WatchedRepo(BaseModel):
    id: str
    user_id: str
    repo_full_name: str
    webhook_id: int
    webhook_secret: str
    active: bool = True


class PRChunk(BaseModel):
    id: str
    pr_id: str
    file_path: str
    hunk_index: int
    language: str
    diff_text: str
    lines_changed: int
    classifier_tag: Optional[str] = None


class Finding(BaseModel):
    id: str
    chunk_id: str
    model_id: str
    severity: Literal["critical", "warning", "info"]
    category: Literal["security", "logic", "style", "performance", "test-coverage"]
    line_number: Optional[int]
    description: str
    suggestion: str
    confidence: float
    accepted: bool = False


class ReviewReport(BaseModel):
    pr_id: str
    pr_url: str
    total_cost_sats: int
    findings: List[Finding]
    summary: str
    critical_count: int
    warning_count: int
    info_count: int
    passed_chunks: int
    model_breakdown: dict


class Transaction(BaseModel):
    id: str
    user_id: str
    to_model_id: str
    amount_sats: int
    chunk_id: str
    timestamp: datetime


class RouterDecision(BaseModel):
    chunk_id: str
    predicted_model_id: str
    predicted_tier_index: int
    confidence: float
    used_router: bool


class ChunkReviewState(BaseModel):
    chunk: PRChunk
    user_id: str
    wallet_id: str = ""
    registry: List[ModelEntry]
    budget_remaining_sats: int
    current_model_id: str
    current_tier_index: int = 0
    worker_output: Optional[str] = None
    findings: List[Finding] = []
    verifier_accepted: bool = False
    router_decision: Optional[RouterDecision] = None
    retry_count: int = 0
    max_retries: int = 2
    chunk_cost_sats: int = 0
    status: Literal["running", "done", "failed", "pending", "classified", "routed", "reviewed", "verified", "escalated"] = "running"
    transactions: List[Transaction] = []
    classifier_tag: Optional[str] = None
    episode: Optional[Any] = None
