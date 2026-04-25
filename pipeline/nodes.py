"""
LangGraph node functions for code review pipeline.

Each node receives ChunkReviewState and returns updated ChunkReviewState.
"""

import logging
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

import httpx
from anthropic import Anthropic
from groq import Groq

from pipeline.chunker import PRChunk
from pipeline.prompts import (
    CLASSIFIER_PROMPT,
    REVIEWER_PROMPT,
    VERIFIER_PROMPT,
    SYNTHESISER_PROMPT,
)

logger = logging.getLogger(__name__)


# ============================================================================
# State & Data Models
# ============================================================================


@dataclass
class Finding:
    """A single finding from code review."""

    issue: str
    severity: str  # "critical", "major", "minor"
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class Episode:
    """A recorded episode of review for a chunk."""

    chunk_id: str
    pr_id: str
    model_id: str
    tier_index: int
    findings: List[Finding]
    verifier_accepted: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ChunkReviewState:
    """State for processing a single code chunk through the review pipeline."""

    # Input
    chunk: PRChunk
    pr_id: str

    # Classification phase
    classifier_tag: Optional[str] = None

    # Router phase
    current_model_id: Optional[str] = None
    current_tier_index: int = 0

    # Reviewer phase
    findings: List[Finding] = field(default_factory=list)

    # Verifier phase
    verifier_accepted: bool = False

    # Escalation tracking
    retry_count: int = 0
    max_retries: int = 3

    # Final episode record
    episode: Optional[Episode] = None

    # Status tracking
    status: str = (
        "pending"  # pending, classified, routed, reviewed, verified, failed, escalated
    )


@dataclass
class ReviewReport:
    """Final review report for a PR."""

    pr_id: str
    total_chunks: int
    chunks_reviewed: int
    summary: str
    priority_actions: List[Dict[str, Any]]
    all_findings: List[Finding]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Classifier Node
# ============================================================================


def classifier_node(state: ChunkReviewState) -> ChunkReviewState:
    """
    Classify the code chunk using Groq API (Llama 3).

    Sets: state.classifier_tag (single word: "logic", "style", "security", etc.)
    Falls back to 'logic' if response invalid.
    """
    try:
        logger.info(f"Classifying chunk {state.chunk.file} for PR {state.pr_id}")

        # Prepare diff text from chunk lines
        diff_text = "\n".join(state.chunk.lines)

        # Call Groq API with Llama 3
        groq_api_key = os.getenv("GROQ_API_KEY")
        groq_client = Groq(api_key=groq_api_key)

        prompt = CLASSIFIER_PROMPT.format(diff_text=diff_text)
        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.3,
        )

        # Parse response - expect single word tag
        tag = response.choices[0].message.content.strip().lower().split()[0]

        # Validate tag (basic validation)
        valid_tags = {
            "logic",
            "style",
            "security",
            "performance",
            "tests",
            "docs",
            "refactor",
        }
        if tag not in valid_tags:
            logger.warning(
                f"Invalid tag '{tag}' for chunk {state.chunk.file}, using 'logic'"
            )
            tag = "logic"

        state.classifier_tag = tag
        state.status = "classified"
        logger.info(f"Chunk {state.chunk.file} classified as: {tag}")

    except Exception as e:
        logger.error(f"Classifier node failed for chunk {state.chunk.file}: {e}")
        state.classifier_tag = "logic"  # fallback
        state.status = "classified"

    return state


# ============================================================================
# Router Node
# ============================================================================


def router_node(state: ChunkReviewState, registry, router) -> ChunkReviewState:
    """
    Route the chunk to appropriate model tier using registry and router.

    Calls: router.predict_model(diff_text, tag, registry)
    Sets: state.current_model_id, state.current_tier_index
    """
    try:
        logger.info(
            f"Routing chunk {state.chunk.file} with tag '{state.classifier_tag}'"
        )

        diff_text = "\n".join(state.chunk.lines)

        # Call router to predict best model
        model_info = router.predict_model(
            diff_text=diff_text,
            tag=state.classifier_tag,
            registry=registry,
        )

        state.current_model_id = model_info.get("model_id")
        state.current_tier_index = model_info.get("tier_index", 0)
        state.status = "routed"

        logger.info(
            f"Chunk routed to model {state.current_model_id} "
            f"at tier {state.current_tier_index}"
        )

    except Exception as e:
        logger.error(f"Router node failed for chunk {state.chunk.file}: {e}")
        # Default to first tier
        state.current_model_id = registry.get_tier(0).get("models", [{}])[0].get("id")
        state.current_tier_index = 0
        state.status = "routed"

    return state


# ============================================================================
# Reviewer Node
# ============================================================================


def reviewer_node(
    state: ChunkReviewState,
    worker_url: str,
    l402_auth: Optional[Dict[str, str]] = None,
) -> ChunkReviewState:
    """
    Send chunk to worker endpoint for review via httpx with L402 support.

    Posts to: /worker/{model_id}
    Parses: findings JSON from response
    """
    try:
        logger.info(
            f"Reviewing chunk {state.chunk.file} with model {state.current_model_id}"
        )

        diff_text = "\n".join(state.chunk.lines)

        # Prepare request payload
        task_payload = {
            "task": REVIEWER_PROMPT.format(
                diff_text=diff_text,
                language=state.chunk.detected_language or "unknown",
                tag=state.classifier_tag,
            ),
            "chunk_id": state.chunk.file,
            "model_id": state.current_model_id,
        }

        # Build headers with L402 auth if provided
        headers = {"Content-Type": "application/json"}
        if l402_auth:
            headers.update(l402_auth)

        # Make request to worker endpoint
        endpoint = f"{worker_url}/worker/{state.current_model_id}"

        with httpx.Client() as client:
            response = client.post(
                endpoint,
                json=task_payload,
                headers=headers,
                timeout=60.0,
            )
            response.raise_for_status()

        # Parse findings from response
        result = response.json()
        findings_data = result.get("findings", [])

        state.findings = [
            Finding(
                issue=f.get("issue"),
                severity=f.get("severity", "minor"),
                line_number=f.get("line_number"),
                suggestion=f.get("suggestion"),
            )
            for f in findings_data
        ]

        state.status = "reviewed"
        logger.info(f"Chunk reviewed, found {len(state.findings)} issues")

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Worker returned error for chunk {state.chunk.file}: {e.response.status_code}"
        )
        state.status = "escalated"
    except Exception as e:
        logger.error(f"Reviewer node failed for chunk {state.chunk.file}: {e}")
        state.status = "escalated"

    return state


# ============================================================================
# Verifier Node
# ============================================================================


def verifier_node(
    state: ChunkReviewState,
    anthropic_client: Anthropic,
    db_store,
) -> ChunkReviewState:
    """
    Verify findings using Claude and write episode to SQLite.

    Calls: anthropic.messages.create() with VERIFIER_PROMPT
    Sets: state.verifier_accepted
    Writes: episode row to DB
    """
    try:
        logger.info(f"Verifying findings for chunk {state.chunk.file}")

        # Format findings for verification
        findings_text = "\n".join(
            [
                f"- {f.severity.upper()}: {f.issue} (line {f.line_number})"
                if f.line_number
                else f"- {f.severity.upper()}: {f.issue}"
                for f in state.findings
            ]
        )

        diff_text = "\n".join(state.chunk.lines)

        # Call Claude verifier
        prompt = VERIFIER_PROMPT.format(
            diff_text=diff_text,
            findings=findings_text,
        )

        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse Claude's verification response
        verifier_response = response.content[0].text.lower()
        state.verifier_accepted = (
            "accept" in verifier_response or "valid" in verifier_response
        )

        logger.info(
            f"Verifier {'accepted' if state.verifier_accepted else 'rejected'} findings"
        )

        # Create and write episode to DB
        state.episode = Episode(
            chunk_id=state.chunk.file,
            pr_id=state.pr_id,
            model_id=state.current_model_id,
            tier_index=state.current_tier_index,
            findings=state.findings,
            verifier_accepted=state.verifier_accepted,
        )

        # Write episode to database
        db_store.write_episode(state.episode)
        logger.info(f"Episode written to database for chunk {state.chunk.file}")

        state.status = "verified"

    except Exception as e:
        logger.error(f"Verifier node failed for chunk {state.chunk.file}: {e}")
        state.status = "escalated"

    return state


# ============================================================================
# Escalate Node
# ============================================================================


def escalate_node(state: ChunkReviewState, registry) -> ChunkReviewState:
    """
    Escalate to next tier or fail if no tier available.

    Calls: registry.get_next_tier()
    Updates: current_model_id, current_tier_index, retry_count
    """
    try:
        logger.info(f"Escalating chunk {state.chunk.file}")

        state.retry_count += 1

        # Try to get next tier
        next_tier = registry.get_next_tier(state.current_tier_index)

        if next_tier is None:
            logger.error(
                f"No tier available after {state.retry_count} retries for chunk {state.chunk.file}"
            )
            state.status = "failed"
            return state

        # Update to next tier
        state.current_tier_index = next_tier.get("index", state.current_tier_index + 1)
        models = next_tier.get("models", [])
        if models:
            state.current_model_id = models[0].get("id")

        logger.info(
            f"Escalated to tier {state.current_tier_index}, "
            f"model {state.current_model_id}"
        )

        # Reset status to route to new model
        state.status = "routed"

    except Exception as e:
        logger.error(f"Escalate node failed for chunk {state.chunk.file}: {e}")
        state.status = "failed"

    return state


# ============================================================================
# Synthesiser Node
# ============================================================================


def synthesiser_node(
    pr_id: str,
    all_findings: List[Finding],
    anthropic_client: Anthropic,
) -> ReviewReport:
    """
    Synthesize all findings from chunks into final PR review report.

    Runs once per PR after all chunks are processed.
    Calls: claude-sonnet with SYNTHESISER_PROMPT
    Returns: ReviewReport with summary + priority_actions
    """
    try:
        logger.info(
            f"Synthesizing review for PR {pr_id} with {len(all_findings)} findings"
        )

        # Group findings by severity
        critical = [f for f in all_findings if f.severity == "critical"]
        major = [f for f in all_findings if f.severity == "major"]
        minor = [f for f in all_findings if f.severity == "minor"]

        # Format findings for Claude
        findings_text = "CRITICAL:\n"
        findings_text += (
            "\n".join([f"- {f.issue}" for f in critical]) if critical else "None\n"
        )
        findings_text += "\nMAJOR:\n"
        findings_text += (
            "\n".join([f"- {f.issue}" for f in major]) if major else "None\n"
        )
        findings_text += "\nMINOR:\n"
        findings_text += (
            "\n".join([f"- {f.issue}" for f in minor]) if minor else "None\n"
        )

        # Call Claude synthesiser
        prompt = SYNTHESISER_PROMPT.format(
            pr_id=pr_id,
            findings=findings_text,
            total_findings=len(all_findings),
        )

        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse Claude's response
        synthesis_text = response.content[0].text

        # Try to extract structured data from response
        # Format: SUMMARY: ..., PRIORITY_ACTIONS: [...]
        priority_actions = []
        if "PRIORITY_ACTIONS:" in synthesis_text:
            try:
                actions_part = synthesis_text.split("PRIORITY_ACTIONS:")[1]
                # Simple parsing - expect JSON array
                json_start = actions_part.find("[")
                json_end = actions_part.rfind("]") + 1
                if json_start >= 0 and json_end > json_start:
                    actions_json = actions_part[json_start:json_end]
                    priority_actions = json.loads(actions_json)
            except (json.JSONDecodeError, IndexError, ValueError) as e:
                logger.warning(f"Could not parse priority actions: {e}")
                priority_actions = [{"action": "Review findings manually"}]

        # Extract summary
        summary = synthesis_text
        if "SUMMARY:" in synthesis_text:
            summary = (
                synthesis_text.split("SUMMARY:")[1]
                .split("PRIORITY_ACTIONS:")[0]
                .strip()
            )

        report = ReviewReport(
            pr_id=pr_id,
            total_chunks=len(set(f.issue for f in all_findings)),  # approximate
            chunks_reviewed=len(set(f.issue for f in all_findings)),  # approximate
            summary=summary,
            priority_actions=priority_actions,
            all_findings=all_findings,
        )

        logger.info(f"Review synthesis complete for PR {pr_id}")
        return report

    except Exception as e:
        logger.error(f"Synthesiser node failed for PR {pr_id}: {e}")
        # Return minimal report on error
        return ReviewReport(
            pr_id=pr_id,
            total_chunks=0,
            chunks_reviewed=0,
            summary=f"Review failed: {str(e)}",
            priority_actions=[{"action": "Review failed - manual review required"}],
            all_findings=all_findings,
        )
