"""Asset Analyzer Stub Worker (WAVE 1 k=1)

Mock worker that returns fixed analysis.json for testing orchestrator.
In k=2, this will be replaced with real narrated_video_producer integration.

ADR-0693: Asset Analyzer Worker
"""

import json
from pathlib import Path


def execute(input_data: dict, state_dir: Path) -> dict:
    """
    Execute asset analysis (STUB version).

    Args:
        input_data: {"ppt_file": str, "output_dir": str}
        state_dir: Directory to write analysis.json

    Returns:
        {"analysis_path": str, "sections": [...]}
    """
    output_dir = Path(input_data["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Stub analysis.json with ready_for_narration = true (Phase gate key)
    analysis = {
        "ready_for_narration": True,
        "sections": [
            {
                "id": "s1",
                "title": "What is CorvinOS?",
                "content": "CorvinOS is an agentic operating system.",
            },
            {
                "id": "s2",
                "title": "Key Features",
                "content": "Skills, Plugins, Learning Loops.",
            },
        ],
        "metadata": {
            "ppt_file": input_data.get("ppt_file", "unknown.pptx"),
            "analysis_timestamp": "2026-09-14T00:00:00Z",
            "deep_read_status": "complete",
        },
    }

    # Write to analysis.json
    analysis_file = output_dir / "analysis.json"
    with open(analysis_file, "w") as f:
        json.dump(analysis, f, indent=2)

    return {
        "analysis_path": str(analysis_file),
        "sections": analysis["sections"],
        "ready_for_narration": True,
    }
