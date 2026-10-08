"""Tests for P3: web_renderer deterministic frame capture."""
import asyncio
import hashlib
from pathlib import Path
import tempfile
import pytest

@pytest.mark.asyncio
async def test_render_web_scene_hero_basic():
    """P3: Render a simple hero slide and verify frames are created."""
    from src.web_renderer import render_web_scene

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)

        scene = {
            "template": "hero",
            "data": {
                "title": "Audit Chain",
                "subtitle": "The foundation of CorvinOS",
            }
        }

        frames = await render_web_scene(scene, duration_s=2.4, out_dir=out_dir, fps=30)

        # Should have at least 1 frame; more if animations detected
        assert len(frames) >= 1, f"expected at least 1 frame, got {len(frames)}"

        # All frames should exist
        for frame in frames:
            assert frame.exists(), f"frame missing: {frame}"
            assert frame.suffix == ".png"
            assert frame.stat().st_size > 0


@pytest.mark.asyncio
async def test_render_web_scene_determinism():
    """P3: Two renders must produce bit-identical frames (determinism proof)."""
    from src.web_renderer import render_web_scene
    
    with tempfile.TemporaryDirectory() as tmpdir1:
        with tempfile.TemporaryDirectory() as tmpdir2:
            scene = {
                "template": "stat",
                "data": {
                    "number": "414",
                    "label": "Tokens Saved",
                    "description": "on a single query vs. baseline",
                }
            }
            
            # Two renders
            frames1 = await render_web_scene(scene, duration_s=1.2, out_dir=Path(tmpdir1), fps=30)
            frames2 = await render_web_scene(scene, duration_s=1.2, out_dir=Path(tmpdir2), fps=30)
            
            assert len(frames1) == len(frames2)
            
            # Compare SHA256 hashes
            hashes1 = [hashlib.sha256(f.read_bytes()).hexdigest() for f in frames1]
            hashes2 = [hashlib.sha256(f.read_bytes()).hexdigest() for f in frames2]
            
            assert hashes1 == hashes2, "frames differ across runs (non-deterministic)"


@pytest.mark.asyncio
async def test_render_web_scene_invalid_template():
    """P3: Invalid template name must raise ValueError."""
    from src.web_renderer import render_web_scene
    
    with tempfile.TemporaryDirectory() as tmpdir:
        scene = {
            "template": "nonexistent",
            "data": {}
        }
        
        with pytest.raises(ValueError, match="unknown template"):
            await render_web_scene(scene, duration_s=1.0, out_dir=Path(tmpdir))


@pytest.mark.asyncio
async def test_render_web_scene_missing_placeholder():
    """P3: Missing placeholder data must raise ValueError."""
    from src.web_renderer import render_web_scene
    
    with tempfile.TemporaryDirectory() as tmpdir:
        scene = {
            "template": "hero",
            "data": {
                "title": "Test",
                # missing "subtitle"
            }
        }
        
        with pytest.raises(ValueError, match="missing placeholder"):
            await render_web_scene(scene, duration_s=1.0, out_dir=Path(tmpdir))


@pytest.mark.asyncio
async def test_render_web_scene_invalid_duration():
    """P3: Duration outside (0, 60] must raise ValueError."""
    from src.web_renderer import render_web_scene

    scene = {"template": "hero", "data": {"title": "T", "subtitle": "S"}}

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="duration must be"):
            await render_web_scene(scene, duration_s=120, out_dir=Path(tmpdir))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
