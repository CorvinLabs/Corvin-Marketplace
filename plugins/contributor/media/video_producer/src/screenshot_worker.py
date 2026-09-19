"""Screenshot Capturer Worker (WAVE 3 k=9–k=12)

Captures console screenshots with metadata.
"""

from pathlib import Path
from typing import Dict

def execute(input_data: Dict, state_dir: Path) -> Dict:
    """Capture screenshots from console."""
    storyboard = input_data.get("storyboard", {})
    console_url = input_data.get("console_url", "http://localhost:8765")
    
    # Stub: create output directory
    screenshots_dir = state_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    
    # In k=10, will use Puppeteer to capture real screenshots
    # For now, create placeholder images
    for i, scene in enumerate(storyboard.get("scenes", []), 1):
        img_file = screenshots_dir / f"scene_{i:02d}.png"
        img_file.write_bytes(b"PNG_STUB")
    
    return {
        "dir": str(screenshots_dir),
        "count": len(storyboard.get("scenes", [])),
    }
