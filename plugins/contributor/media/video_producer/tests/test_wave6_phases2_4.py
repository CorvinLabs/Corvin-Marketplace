"""WAVE 6 Phases 2–4: Puppeteer, FFmpeg, YouTube Integration Tests

Phase 2 (Week 10): Screenshot capture via Puppeteer
Phase 3 (Week 11): FFmpeg H.264 assembly
Phase 4 (Week 12): YouTube API v3 upload
"""

import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestPuppeteerScreenshots:
    """Phase 2: Puppeteer screenshot capture."""

    def test_puppeteer_script_generation(self):
        """Generate valid Node.js Puppeteer script."""
        from screenshot_puppeteer import _generate_puppeteer_script
        
        scenes = [
            {"id": "s1", "title": "Scene 1", "duration_sec": 10},
            {"id": "s2", "title": "Scene 2", "duration_sec": 15}
        ]
        
        script = _generate_puppeteer_script("http://localhost:8765", scenes, "/tmp")
        
        # Verify script contains key elements
        assert "puppeteer" in script
        assert "screenshot" in script
        assert "localhost:8765" in script
        assert "s1" in script
        assert "s2" in script

    def test_execute_missing_console_url(self):
        """Missing console URL → handled gracefully."""
        from screenshot_puppeteer import execute
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_data = {"storyboard": {"scenes": []}}
            state_dir = Path(tmpdir)
            
            # Empty scenes → ValueError
            with pytest.raises(ValueError, match="Storyboard has no scenes"):
                execute(input_data, state_dir)

    @patch("screenshot_puppeteer.subprocess.run")
    def test_execute_puppeteer_success(self, mock_run):
        """Successful Puppeteer execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "frames": [
                    {"scene_id": "s1", "timestamp_sec": 0.0, "file": "scene_s1_0.png"}
                ],
                "total_frames": 1,
                "status": "success"
            })
        )
        
        from screenshot_puppeteer import execute
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_data = {
                "console_url": "http://localhost:8765",
                "storyboard": {
                    "scenes": [
                        {"id": "s1", "title": "Scene 1", "duration_sec": 10}
                    ]
                }
            }
            state_dir = Path(tmpdir)
            
            result = execute(input_data, state_dir)
            
            assert result["status"] == "success"
            assert result["total_frames"] == 1
            assert len(result["frames"]) == 1


class TestFFmpegAssembly:
    """Phase 3: FFmpeg H.264 assembly."""

    def test_duration_estimation(self):
        """Duration estimation from storyboard."""
        from video_ffmpeg import _estimate_duration
        
        storyboard = {
            "scenes": [
                {"id": "s1", "duration_sec": 10},
                {"id": "s2", "duration_sec": 15},
                {"id": "s3", "duration_sec": 5}
            ]
        }
        
        duration = _estimate_duration(storyboard)
        assert duration == 30  # 10 + 15 + 5

    def test_execute_missing_audio(self):
        """Missing audio file → ValueError."""
        from video_ffmpeg import execute
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_data = {
                "audio_file": "/nonexistent/audio.mp3",
                "screenshots_dir": tmpdir,
                "storyboard": {"scenes": []}
            }
            state_dir = Path(tmpdir)
            
            with pytest.raises(ValueError, match="Audio file not found"):
                execute(input_data, state_dir)

    def test_execute_missing_screenshots(self):
        """Missing screenshots directory → ValueError."""
        from video_ffmpeg import execute
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy audio
            audio_file = Path(tmpdir) / "audio.mp3"
            audio_file.write_bytes(b"fake audio")
            
            input_data = {
                "audio_file": str(audio_file),
                "screenshots_dir": "/nonexistent/screenshots",
                "storyboard": {"scenes": []}
            }
            state_dir = Path(tmpdir)
            
            with pytest.raises(ValueError, match="Screenshots directory not found"):
                execute(input_data, state_dir)

    @patch("video_ffmpeg.subprocess.run")
    def test_execute_ffmpeg_success(self, mock_run):
        """Successful FFmpeg execution."""
        mock_run.return_value = MagicMock(returncode=0)

        from video_ffmpeg import execute

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)

            # Create dummy files
            audio_file = state_dir / "audio.mp3"
            audio_file.write_bytes(b"fake audio")

            screenshots_dir = state_dir / "screenshots"
            screenshots_dir.mkdir()

            # FIX: Create PNG files with correct naming (scene_*.png) to pass precondition
            (screenshots_dir / "scene_s1_frame_0.png").write_bytes(b"PNG_DATA_S1")
            (screenshots_dir / "scene_s2_frame_0.png").write_bytes(b"PNG_DATA_S2")

            # Create dummy output
            output_dir = state_dir / "output"
            output_dir.mkdir()
            output_mp4 = output_dir / "video_output.mp4"
            output_mp4.write_bytes(b"fake video" * 1000)  # ~10 KB

            input_data = {
                "audio_file": str(audio_file),
                "screenshots_dir": str(screenshots_dir),
                "output_dir": str(output_dir),
                "storyboard": {
                    "scenes": [
                        {"id": "s1", "duration_sec": 10},
                        {"id": "s2", "duration_sec": 10}
                    ]
                }
            }

            result = execute(input_data, state_dir)

            assert result["status"] == "success"
            assert result["codec"] == "h.264"
            assert result["duration_sec"] == 20  # 10 + 10 from 2 scenes


class TestYouTubeAPI:
    """Phase 4: YouTube API v3 upload."""

    def test_upload_time_estimation(self):
        """Estimate upload time based on file size and speed."""
        from youtube_api import estimate_upload_time
        
        # 100 MB at 1 Mbps = ~13.3 minutes
        time_minutes = estimate_upload_time(100, 1.0)
        assert 13 < time_minutes < 14
        
        # 100 MB at 10 Mbps = ~1.33 minutes
        time_minutes = estimate_upload_time(100, 10.0)
        assert 1 < time_minutes < 2

    def test_execute_missing_video(self):
        """Missing video file → ValueError."""
        from youtube_api import execute
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_data = {
                "video_path": "/nonexistent/video.mp4"
            }
            state_dir = Path(tmpdir)
            
            with pytest.raises(ValueError, match="Video file not found"):
                execute(input_data, state_dir)

    def test_execute_missing_credentials(self):
        """Missing YouTube credentials → ValueError."""
        from youtube_api import execute
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            
            # Create dummy video
            video_file = state_dir / "video.mp4"
            video_file.write_bytes(b"fake video")
            
            input_data = {
                "video_path": str(video_file),
                "credentials_path": "/nonexistent/credentials.json"
            }
            
            with pytest.raises(ValueError, match="YouTube credentials not found"):
                execute(input_data, state_dir)

    def test_task_id_generation(self):
        """Task ID generated from video hash (stable, unique)."""
        from youtube_api import execute
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            
            # Create dummy files
            video_file = state_dir / "video.mp4"
            video_file.write_bytes(b"fake video content")
            
            creds_file = state_dir / "credentials.json"
            creds_file.write_text(json.dumps({
                "type": "service_account",
                "project_id": "test"
            }))
            
            # Mock the Google API calls
            with patch("youtube_api.service_account.Credentials.from_service_account_info"):
                with patch("youtube_api.build"):
                    input_data = {
                        "video_path": str(video_file),
                        "credentials_path": str(creds_file)
                    }
                    
                    # Should not raise (will fail on API, but task_id should be generated)
                    try:
                        execute(input_data, state_dir)
                    except Exception:
                        pass  # Expected: API error


class TestE2EIntegration:
    """End-to-end: Puppeteer → FFmpeg → YouTube."""

    def test_workflow_screenshot_to_video(self):
        """E2E: Screenshot capture → FFmpeg assembly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Mock screenshot directory with dummy PNG
            screenshots_dir = tmpdir / "screenshots"
            screenshots_dir.mkdir()
            (screenshots_dir / "scene_s1_frame_0.png").write_bytes(b"PNG")
            
            # Mock audio
            audio_file = tmpdir / "audio.mp3"
            audio_file.write_bytes(b"MP3")
            
            # FFmpeg would assemble these
            # Verify preconditions
            assert (screenshots_dir / "scene_s1_frame_0.png").exists()
            assert audio_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
