import os
import yaml
from typing import List, Optional

from models import ModelEntry

REGISTRY_PATH = os.environ.get("REGISTRY_PATH", "./registry.yaml")


def load_registry(path: str = REGISTRY_PATH) -> List[ModelEntry]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    models = [ModelEntry(**m) for m in data["models"]]
    models.sort(key=lambda m: m.cost_sats)
    return models


def get_sorted_models(registry: List[ModelEntry]) -> List[ModelEntry]:
    return sorted(registry, key=lambda m: m.cost_sats)


def get_model_by_id(registry: List[ModelEntry], model_id: str) -> Optional[ModelEntry]:
    return next((m for m in registry if m.id == model_id), None)


def get_next_tier(registry: List[ModelEntry], current_id: str) -> Optional[ModelEntry]:
    for i, model in enumerate(registry):
        if model.id == current_id:
            return registry[i + 1] if i + 1 < len(registry) else None
    return None


def get_models_by_tag(registry: List[ModelEntry], tag: str) -> List[ModelEntry]:
    return [m for m in registry if tag in m.capability_tags]
