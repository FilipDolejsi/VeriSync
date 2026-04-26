class Router:
    """
    Stub for the RL router.
    Currently always routes the chunk to tier 0 (the cheapest tier) and its default model.
    """
    def __init__(self):
        pass

    def predict_model(self, diff_text: str, tag: str, registry) -> dict:
        """
        Predict the best model for a given chunk.
        Always returns tier 0.
        """
        model_id = "default"
        
        # Assuming registry is wrapped by RegistryWrapper with get_tier
        if hasattr(registry, "get_tier"):
            tier = registry.get_tier(0)
            if tier and "models" in tier and tier["models"]:
                model_id = tier["models"][0].get("id", "default")
        # Assuming registry is a list of ModelEntry (from loader.py)
        elif isinstance(registry, list) and len(registry) > 0:
            model_id = registry[0].id
            
        return {
            "model_id": model_id,
            "tier_index": 0
        }
