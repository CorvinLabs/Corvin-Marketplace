"""Week 10: Real Puppeteer Screenshot Integration

Captures console screenshots via Node.js Puppeteer subprocess.
"""

import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, List
import tempfile

logger = logging.getLogger(__name__)


def execute(input_data: Dict, state_dir: Path) -> Dict:
    """Capture console screenshots via Puppeteer (Node.js subprocess).
    
    Preconditions:
    - Node.js installed
    - Puppeteer npm module available
    - Console running at http://localhost:8765
    
    Returns:
        {
            "dir": str,  # Screenshot directory path
            "frames": [
                {
                    "scene_id": "s1",
                    "timestamp_sec": 0.0,
                    "file": "scene_s1_frame_0.png"
                }
            ],
            "total_frames": int
        }
    """
    console_url = input_data.get("console_url", "http://localhost:8765")
    storyboard = input_data.get("storyboard", {})
    scenes = storyboard.get("scenes", [])
    
    if not scenes:
        raise ValueError("Storyboard has no scenes")
    
    # Create output directory
    screenshots_dir = state_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    
    # Generate Puppeteer script
    puppeteer_script = _generate_puppeteer_script(console_url, scenes, str(screenshots_dir))
    
    # Write script to temp file
    script_file = state_dir / "capture_screenshots.js"
    script_file.write_text(puppeteer_script)
    
    # Execute via Node.js
    try:
        result = subprocess.run(
            ["node", str(script_file)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
            cwd=str(state_dir)
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Puppeteer script failed: {result.stderr}")
        
        # Parse output
        output_json = result.stdout.strip()
        if not output_json:
            raise RuntimeError("Puppeteer script produced no output")
        
        output = json.loads(output_json)
        
        return {
            "dir": str(screenshots_dir),
            "frames": output.get("frames", []),
            "total_frames": output.get("total_frames", 0),
            "status": "success"
        }
    
    except FileNotFoundError:
        raise RuntimeError("Node.js not found. Install: https://nodejs.org/")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Puppeteer screenshot capture timed out (>5 min)")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid Puppeteer output: {e}")
    except Exception as e:
        raise RuntimeError(f"Puppeteer screenshot capture failed: {e}")


def _generate_puppeteer_script(console_url: str, scenes: List[Dict], output_dir: str) -> str:
    """Generate Node.js Puppeteer script for screenshot capture."""
    
    scenes_json = json.dumps(scenes)
    
    return f"""
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

(async () => {{
  const browser = await puppeteer.launch({{headless: 'new'}});
  const page = await browser.newPage();
  
  const scenes = {scenes_json};
  const frames = [];
  let totalFrames = 0;
  
  for (const scene of scenes) {{
    try {{
      // Navigate to console URL with scene parameter
      const sceneUrl = `{console_url}?scene=${{scene.id}}`;
      await page.goto(sceneUrl, {{waitUntil: 'networkidle2', timeout: 30000}});
      
      // Wait for content to render
      await page.waitForTimeout(1000);
      
      // Take screenshot
      const filename = `scene_${{scene.id}}_frame_0.png`;
      const filepath = path.join('{output_dir}', filename);
      
      await page.screenshot({{path: filepath, fullPage: false}});
      
      frames.push({{
        scene_id: scene.id,
        timestamp_sec: (frames.length * (scene.duration_sec || 10)),
        file: filename
      }});
      
      totalFrames++;
    }} catch (e) {{
      console.error(`Failed to capture scene ${{scene.id}}: ${{e.message}}`);
    }}
  }}
  
  // Output JSON result
  console.log(JSON.stringify({{
    frames: frames,
    total_frames: totalFrames,
    status: 'success'
  }}));
  
  await browser.close();
}})();
"""


if __name__ == "__main__":
    import sys
    # Simple test: generate script and print
    test_scenes = [
        {"id": "s1", "title": "Scene 1", "duration_sec": 10},
        {"id": "s2", "title": "Scene 2", "duration_sec": 10}
    ]
    script = _generate_puppeteer_script("http://localhost:8765", test_scenes, "/tmp/screenshots")
    print(script)
