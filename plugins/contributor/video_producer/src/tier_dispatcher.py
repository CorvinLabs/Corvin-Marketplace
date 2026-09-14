"""Tier Dispatcher (WAVE 1 k=5)

4-tier fallback routing: Blender → Manim → Three.js → SVG
"""

import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

def execute(input_data: Dict, state_dir: Path) -> Dict:
    """Route to appropriate rendering tier."""
    tier_preference = input_data.get("tier_preference", "auto")
    logger.info(f"Tier dispatcher: {tier_preference}")
    
    if tier_preference == "auto" or tier_preference == "blender":
        return {"tier": 3, "renderer": "blender_cycles"}
    elif tier_preference == "manim":
        return {"tier": 2, "renderer": "manim"}
    elif tier_preference == "three.js":
        return {"tier": 1.5, "renderer": "three.js"}
    else:
        return {"tier": 1, "renderer": "svg"}
