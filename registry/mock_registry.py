"""
Mock registry backed by hardcoded entries. Used in tests and offline development.
Exposes the same interface as loader.py — function signatures must stay in sync.
"""

from typing import List, Optional

from models import ModelEntry

MOCK_REGISTRY: List[ModelEntry] = [
    ModelEntry(
        id="llama3-8b",
        name="llama3:8b",
        provider="ollama",
        cost_sats=5,
        endpoint_url="http://localhost:11434/api/generate",
        capability_tags=["style", "classify", "logic"],
    ),
    ModelEntry(
        id="mistral-7b",
        name="mistral:7b",
        provider="ollama",
        cost_sats=15,
        endpoint_url="http://localhost:11434/api/generate",
        capability_tags=["logic", "security"],
    ),
    ModelEntry(
        id="claude-haiku",
        name="claude-haiku-4-5-20251001",
        provider="anthropic",
        cost_sats=50,
        endpoint_url="https://api.anthropic.com/v1/messages",
        capability_tags=["security", "architecture", "logic"],
    ),
]


def load_registry(path: str = None) -> List[ModelEntry]:
    """Return MOCK_REGISTRY regardless of path."""
    return list(MOCK_REGISTRY)


def get_sorted_models(registry: List[ModelEntry]) -> List[ModelEntry]:
    return registry


def get_next_tier(registry: List[ModelEntry], current_id: str) -> Optional[ModelEntry]:
    for i, model in enumerate(registry):
        if model.id == current_id:
            if i + 1 < len(registry):
                return registry[i + 1]
            return None
    return None


def get_model_by_id(registry: List[ModelEntry], model_id: str) -> Optional[ModelEntry]:
    for model in registry:
        if model.id == model_id:
            return model
    return None


def get_models_by_tag(registry: List[ModelEntry], tag: str) -> List[ModelEntry]:
    return [model for model in registry if tag in model.capability_tags]
