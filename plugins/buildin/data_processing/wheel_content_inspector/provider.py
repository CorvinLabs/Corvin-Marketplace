"""Plugin provider: wheel_content_inspector."""

class Plugin:
    """Provider for wheel_content_inspector."""
    
    def invoke(self, capability_id, input_data, **kwargs):
        """Invoke the capability."""
        return {"status": "ok"}
