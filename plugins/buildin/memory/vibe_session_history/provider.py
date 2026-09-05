"""Plugin provider: vibe_session_history."""

class Plugin:
    """Provider for vibe_session_history."""
    
    def invoke(self, capability_id, input_data, **kwargs):
        """Invoke the capability."""
        return {"status": "ok"}
