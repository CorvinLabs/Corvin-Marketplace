"""Plugin provider: user_model_learner."""

class Plugin:
    """Provider for user_model_learner."""
    
    def invoke(self, capability_id, input_data, **kwargs):
        """Invoke the capability."""
        return {"status": "ok"}
