"""Week 10: Real Puppeteer Screenshot Capture

Uses Puppeteer (Node.js) to capture console screenshots.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict

def execute(input_data: Dict, state_dir: Path) -> Dict:
    """Capture screenshots via Puppeteer (real console capture)."""
    storyboard = input_data.get("storyboard", {})
    console_url = input_data.get("console_url", "http://localhost:8765")
    
    screenshots_dir = state_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    
    # Week 10: Call real Puppeteer via Node.js subprocess
    node_script = f"""
    const puppeteer = require('puppeteer');
    
    (async () => {{
        const browser = await puppeteer.launch();
        const page = await browser.newPage();
        await page.goto('{console_url}', {{waitUntil: 'networkidle2'}});
        
        const scenes = {json.dumps(storyboard.get('scenes', []))};
        for (let i = 0; i < scenes.length; i++) {{
            const filename = `{screenshots_dir}/scene_${{(i+1).toString().padStart(2, '0')}}.png`;
            await page.screenshot({{path: filename, fullPage: true}});
        }}
        
        await browser.close();
    }})();
    """
    
    try:
        # Run Puppeteer script
        result = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Puppeteer failed: {result.stderr}")
        
        # Count generated screenshots
        screenshots = list(screenshots_dir.glob("scene_*.png"))
        
        return {
            "dir": str(screenshots_dir),
            "count": len(screenshots),
            "captured": True,
        }
    
    except FileNotFoundError:
        raise ImportError("node/puppeteer not installed: npm install puppeteer")
    except Exception as e:
        raise RuntimeError(f"Screenshot capture failed: {e}")
