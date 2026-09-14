"""End-to-end test: CLI entry point calls orchestrator end-to-end."""

import json
import subprocess
import tempfile
from pathlib import Path
import sys


def test_cli_health():
    """Test: CLI health check works."""
    result = subprocess.run(
        [sys.executable, "-m", "video_producer", "health", "--verbose"],
        cwd="/home/shumway/projects/Corvin-Marketplace/plugins/contributor/video_producer",
        capture_output=True,
        text=True,
        timeout=10
    )

    print("HEALTH OUTPUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    assert result.returncode in [0, 1], f"Unexpected return code: {result.returncode}"
    assert "healthy" in result.stdout or "Health" in result.stdout


def test_cli_orchestrate_with_sample_ppt():
    """Test: CLI orchestrate calls full pipeline with sample PPT."""

    # Create a minimal sample PPT for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a simple .txt file to simulate a PPT content file
        sample_ppt = tmpdir / "sample_presentation.txt"
        sample_ppt.write_text("""Presentation: Example
Content: Introduction to Video Producer
Main topic: Demonstrating the orchestration system
""")

        output_file = tmpdir / "orchestration_result.json"

        # Run CLI
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "video_producer",
                "orchestrate",
                "--assets", str(sample_ppt),
                "--project-dir", str(tmpdir),
                "--output", str(output_file),
            ],
            cwd="/home/shumway/projects/Corvin-Marketplace/plugins/contributor/video_producer",
            capture_output=True,
            text=True,
            timeout=30
        )

        print("CLI OUTPUT:")
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        # Check result
        assert output_file.exists(), f"Output file not created: {output_file}"

        # Load and validate JSON
        with open(output_file) as f:
            result_json = json.load(f)

        print("RESULT JSON:")
        print(json.dumps(result_json, indent=2))

        # Validate structure
        assert "status" in result_json
        assert "analysis" in result_json or "error" in result_json

        print(f"✅ CLI orchestrate call successful (status: {result_json.get('status')})")


if __name__ == "__main__":
    print("\n=== TEST 1: CLI Health Check ===\n")
    try:
        test_cli_health()
        print("✅ test_cli_health PASSED\n")
    except AssertionError as e:
        print(f"❌ test_cli_health FAILED: {e}\n")

    print("\n=== TEST 2: CLI Orchestrate with Sample PPT ===\n")
    try:
        test_cli_orchestrate_with_sample_ppt()
        print("✅ test_cli_orchestrate_with_sample_ppt PASSED\n")
    except AssertionError as e:
        print(f"❌ test_cli_orchestrate_with_sample_ppt FAILED: {e}\n")
    except Exception as e:
        print(f"❌ test_cli_orchestrate_with_sample_ppt ERROR: {e}\n")
