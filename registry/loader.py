import yaml
from typing import List, Optional

from models import ModelEntry


def load_registry(path: str) -> List[ModelEntry]:
    """
    Parse and validate registry.yaml.
    Returns a list of ModelEntry, sorted by cost_sats ascending.
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        
    models_list = []
    if data and 'models' in data:
        for entry_data in data['models']:
            models_list.append(ModelEntry(**entry_data))
            
    # Sort by cost_sats ascending
    models_list.sort(key=lambda x: x.cost_sats)
    return models_list


def get_sorted_models(registry: List[ModelEntry]) -> List[ModelEntry]:
    """
    Returns the sorted list of models.
    Assuming the input list is already sorted by load_registry.
    """
    return registry


def get_next_tier(registry: List[ModelEntry], current_id: str) -> Optional[ModelEntry]:
    """
    Find current model index in sorted list.
    Returns entry at index+1 or None if at top/not found.
    """
    for i, model in enumerate(registry):
        if model.id == current_id:
            if i + 1 < len(registry):
                return registry[i + 1]
            return None
    return None


def get_model_by_id(registry: List[ModelEntry], model_id: str) -> Optional[ModelEntry]:
    """
    Lookup model by its id field.
    """
    for model in registry:
        if model.id == model_id:
            return model
    return None


def get_models_by_tag(registry: List[ModelEntry], tag: str) -> List[ModelEntry]:
    """
    Filter registry entries where tag in entry.capability_tags.
    """
    return [model for model in registry if tag in model.capability_tags]
