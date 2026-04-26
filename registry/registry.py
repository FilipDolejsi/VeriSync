from typing import List, Dict, Optional, Any
from models import ModelEntry

class Registry:
    """
    Wraps the loaded model registry list to provide tier-based lookups
    expected by the pipeline nodes (like get_tier and get_next_tier).
    """
    def __init__(self, models_list: List[ModelEntry]):
        self.models_list = models_list

    def get_tier(self, index: int) -> Optional[Dict[str, Any]]:
        """
        Returns a dictionary representing a tier at the given index.
        Assuming models are sorted by cost_sats, each index is its own tier.
        """
        if 0 <= index < len(self.models_list):
            # nodes.py expects a dictionary with "index" and a list of "models"
            return {
                "index": index,
                "models": [{"id": self.models_list[index].id}]
            }
        return None

    def get_next_tier(self, current_index: int) -> Optional[Dict[str, Any]]:
        """
        Returns the next tier (current_index + 1) if available.
        """
        return self.get_tier(current_index + 1)
