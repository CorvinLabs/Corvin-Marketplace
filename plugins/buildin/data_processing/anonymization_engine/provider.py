"""Plugin provider: anonymization_engine."""

class Plugin:
    """Provider for anonymization_engine."""
    
    def invoke(self, capability_id, input_data, **kwargs):
        """Invoke the capability."""
        return {"status": "ok"}
