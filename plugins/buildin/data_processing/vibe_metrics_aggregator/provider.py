"""Plugin provider: vibe_metrics_aggregator."""

class Plugin:
    """Provider for vibe_metrics_aggregator."""
    
    def invoke(self, capability_id, input_data, **kwargs):
        """Invoke the capability."""
        return {"status": "ok"}
