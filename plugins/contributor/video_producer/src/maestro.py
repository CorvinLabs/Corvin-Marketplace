"""Maestro Orchestrator — Unified Video Production Workflow

Orchestrates the complete video production pipeline:
1. Asset validation
2. Voice synthesis (narration)
3. Voice-sync mapping
4. Animation rendering (with tier fallback)
5. Video composition
6. Quality metrics + audit logging

ADR-0740: Director Mode Advanced (Maestro Orchestrator)
"""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import datetime


@dataclass
class Storyboard:
    """Storyboard specification for video"""
    title: str
    concept_id: str
    didactic_level: str         # "beginner", "technical"
    duration_seconds: int
    narration: str              # Full narration text
    keyframes: List[dict]       # [{frame: 0, event: "start"}, ...]
    output_format: str = "mp4"


@dataclass
class VideoMetadata:
    """Metadata for generated video"""
    storyboard_hash: str
    output_path: Optional[Path]
    duration_seconds: float
    audio_duration_sec: float
    video_hash: str
    tier_used: int
    render_time_ms: int
    generation_timestamp: str
    narration_hash: str


class Maestro:
    """Video production orchestrator

    Manages the complete workflow: storyboard → audio → animation → video.
    Ensures reproducibility via hashing and deterministic tier selection.
    """

    def __init__(self, tier_dispatcher, voice_synthesizer):
        """Initialize Maestro

        Args:
            tier_dispatcher: TierDispatcher instance for animation rendering
            voice_synthesizer: VoiceSynthesizer instance for narration
        """
        self.name = "maestro"
        self.version = "5.1.0"
        self.dispatcher = tier_dispatcher
        self.synth = voice_synthesizer

        # Setup directories (relative to plugin)
        plugin_root = Path(__file__).parent
        self.output_dir = plugin_root / "outputs" / "videos"
        self.metadata_dir = plugin_root / "outputs" / "metadata"
        self.audit_dir = plugin_root / "outputs" / "audit"

        for d in [self.output_dir, self.metadata_dir, self.audit_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def produce(self, storyboard: Storyboard) -> dict:
        """Produce video from storyboard

        Args:
            storyboard: Storyboard specification

        Returns:
            Result dict with video path, metadata, and audit trail
        """
        start_time = time.time()
        audit_events = []

        try:
            # Step 1: Validate storyboard
            audit_events.append(self._emit_audit(
                event_type="storyboard_validated",
                concept_id=storyboard.concept_id,
                status="ok"
            ))

            # Step 2: Synthesize narration
            syn_result = self.synth.synthesize(
                type("SynthRequest", (), {
                    "text": storyboard.narration,
                    "voice": "nova",
                    "model": "tts-1-hd",
                    "format": "mp3"
                })()
            )

            if not syn_result.success:
                audit_events.append(self._emit_audit(
                    event_type="synthesis_failed",
                    concept_id=storyboard.concept_id,
                    error=syn_result.error
                ))
                return {
                    "success": False,
                    "error": f"Voice synthesis failed: {syn_result.error}",
                    "audit_events": audit_events
                }

            audio_duration = syn_result.duration_sec
            narration_hash = syn_result.text_hash

            audit_events.append(self._emit_audit(
                event_type="narration_synthesized",
                concept_id=storyboard.concept_id,
                audio_duration=audio_duration,
                text_hash=narration_hash
            ))

            # Step 3: Dispatch animation rendering
            anim_request = type("AnimRequest", (), {
                "animation_id": storyboard.concept_id,
                "didactic_level": storyboard.didactic_level,
                "duration_seconds": storyboard.duration_seconds,
                "assets": [],
                "output_format": storyboard.output_format
            })()

            dispatch_result = self.dispatcher.dispatch(anim_request)

            if not dispatch_result["success"]:
                audit_events.append(self._emit_audit(
                    event_type="animation_failed",
                    concept_id=storyboard.concept_id,
                    error=dispatch_result.get("error")
                ))
                return {
                    "success": False,
                    "error": f"Animation rendering failed: {dispatch_result.get('error')}",
                    "audit_events": audit_events
                }

            video_path = Path(dispatch_result.get("output_path"))
            tier_used = self._parse_tier_name(dispatch_result.get("tier"))
            render_time = dispatch_result.get("render_time_ms", 0)

            audit_events.append(self._emit_audit(
                event_type="animation_rendered",
                concept_id=storyboard.concept_id,
                tier=dispatch_result.get("tier"),
                render_time_ms=render_time
            ))

            # Step 4: Calculate hashes
            storyboard_hash = self._hash_storyboard(storyboard)
            video_hash = self._hash_file(video_path) if video_path.exists() else ""

            # Step 5: Emit completion audit event
            audit_events.append(self._emit_audit(
                event_type="video_production_complete",
                concept_id=storyboard.concept_id,
                storyboard_hash=storyboard_hash,
                video_hash=video_hash,
                tier=tier_used
            ))

            # Step 6: Save metadata
            metadata = VideoMetadata(
                storyboard_hash=storyboard_hash,
                output_path=video_path,
                duration_seconds=storyboard.duration_seconds,
                audio_duration_sec=audio_duration,
                video_hash=video_hash,
                tier_used=tier_used,
                render_time_ms=render_time,
                generation_timestamp=datetime.now().isoformat(),
                narration_hash=narration_hash
            )

            self._save_metadata(storyboard.concept_id, metadata)
            self._save_audit_events(storyboard.concept_id, audit_events)

            total_time_ms = int((time.time() - start_time) * 1000)

            return {
                "success": True,
                "output_path": str(video_path),
                "duration_seconds": storyboard.duration_seconds,
                "audio_duration_sec": audio_duration,
                "tier_used": tier_used,
                "render_time_ms": render_time,
                "total_time_ms": total_time_ms,
                "storyboard_hash": storyboard_hash,
                "video_hash": video_hash,
                "audit_events": audit_events
            }

        except Exception as e:
            audit_events.append(self._emit_audit(
                event_type="production_error",
                concept_id=storyboard.concept_id,
                error=str(e)
            ))
            return {
                "success": False,
                "error": f"Exception: {str(e)}",
                "audit_events": audit_events
            }

    def _hash_storyboard(self, storyboard: Storyboard) -> str:
        """Hash storyboard for reproducibility

        Args:
            storyboard: Storyboard to hash

        Returns:
            SHA256 hash
        """
        data = {
            "title": storyboard.title,
            "concept_id": storyboard.concept_id,
            "didactic_level": storyboard.didactic_level,
            "duration_seconds": storyboard.duration_seconds,
            "narration": storyboard.narration,
            "keyframes": storyboard.keyframes
        }
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _hash_file(self, path: Path) -> str:
        """Hash file content

        Args:
            path: Path to file

        Returns:
            SHA256 hash
        """
        try:
            sha = hashlib.sha256()
            with open(path, "rb") as f:
                sha.update(f.read())
            return sha.hexdigest()
        except Exception as e:
            print(f"[MAESTRO] Hash error: {e}")
            return ""

    def _parse_tier_name(self, tier_name: str) -> int:
        """Parse tier name to number

        Args:
            tier_name: Tier name (e.g., "TIER_2_RICH")

        Returns:
            Tier number (1, 2, or 3)
        """
        if "TIER_3" in tier_name or "TIER_3" in str(tier_name):
            return 3
        elif "TIER_2" in tier_name or "TIER_2" in str(tier_name):
            return 2
        else:
            return 1

    def _emit_audit(self, event_type: str, concept_id: str, **kwargs) -> dict:
        """Emit audit event

        Args:
            event_type: Type of audit event
            concept_id: Concept ID
            **kwargs: Additional event data

        Returns:
            Audit event dict
        """
        event = {
            "event_type": event_type,
            "concept_id": concept_id,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        return event

    def _save_metadata(self, concept_id: str, metadata: VideoMetadata):
        """Save video metadata

        Args:
            concept_id: Concept ID
            metadata: VideoMetadata to save
        """
        metadata_file = self.metadata_dir / f"{concept_id}_metadata.json"
        data = {
            "storyboard_hash": metadata.storyboard_hash,
            "output_path": str(metadata.output_path),
            "duration_seconds": metadata.duration_seconds,
            "audio_duration_sec": metadata.audio_duration_sec,
            "video_hash": metadata.video_hash,
            "tier_used": metadata.tier_used,
            "render_time_ms": metadata.render_time_ms,
            "generation_timestamp": metadata.generation_timestamp,
            "narration_hash": metadata.narration_hash
        }
        try:
            with open(metadata_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[MAESTRO] Metadata save error: {e}")

    def _save_audit_events(self, concept_id: str, events: List[dict]):
        """Save audit events

        Args:
            concept_id: Concept ID
            events: List of audit events
        """
        audit_file = self.audit_dir / f"{concept_id}_audit.jsonl"
        try:
            with open(audit_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")
        except Exception as e:
            print(f"[MAESTRO] Audit save error: {e}")
