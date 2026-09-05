"""Plugin provider: artifact_extraction."""

class Plugin:
    """Provider for artifact_extraction."""
    
    def invoke(self, capability_id, input_data, **kwargs):
        """Invoke the capability."""
        return {"status": "ok"}
