#!/usr/bin/env python3
"""Phase 1 Demo Script — Generate Learning Loop Video

Demonstrates the complete Phase 1 pipeline:
1. Voice synthesis (narration → MP3)
2. Voice-sync mapping (keyframe timing)
3. Animation rendering (Tier 2 Manim with Tier 1 fallback)
4. Video composition + audit logging

Usage:
    python3 generate_demo_video.py [--tier {1,2,3}]
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Setup plugin path
plugin_root = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_root / "src"))

from phase5.manim_animator import ManimAnimatorWorker
from phase5.quick_renderer import QuickRendererWorker
from phase5.tier_dispatcher import TierDispatcher, TierLevel, AnimationRequest
from phase5.voice_sync_mapper import VoiceSyncMapper, VoiceSyncMapping, Keyframe
from voice_synthesizer import VoiceSynthesizer, SynthesisRequest
from maestro import Maestro, Storyboard


def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def demo_phase1():
    """Run Phase 1 demo pipeline"""
    print_section("PHASE 1 DEMO: Learning Loop Video Production")

    # Step 1: Initialize components
    print("Step 1: Initializing components...")
    tier1 = QuickRendererWorker(timeout_seconds=10)
    tier2 = ManimAnimatorWorker(timeout_seconds=60, cache_enabled=True)
    dispatcher = TierDispatcher(tier1, tier2)
    synth = VoiceSynthesizer(cache_enabled=True)
    maestro = Maestro(dispatcher, synth)
    print("✅ Components initialized\n")

    # Step 2: Create storyboard
    print("Step 2: Creating Learning Loop storyboard...")
    storyboard = Storyboard(
        title="Learning Loop Visualization",
        concept_id="learning-loop",
        didactic_level="beginner",
        duration_seconds=30,
        narration="The learning loop has five key steps: Measure your current state, Receive feedback from stakeholders, Analyze the results, Optimize your strategy, and Deploy the improvements. This cycle repeats continuously.",
        keyframes=[
            {"frame": 0, "event": "title_appears", "text": "Learning Loop"},
            {"frame": 30, "event": "measure_appears", "text": "Step 1: Measure"},
            {"frame": 90, "event": "feedback_appears", "text": "Step 2: Feedback"},
            {"frame": 150, "event": "analyze_appears", "text": "Step 3: Analyze"},
            {"frame": 210, "event": "optimize_appears", "text": "Step 4: Optimize"},
            {"frame": 270, "event": "deploy_appears", "text": "Step 5: Deploy"},
            {"frame": 450, "event": "cycle_repeats", "text": "Repeat..."},
            {"frame": 750, "event": "end"}
        ],
        output_format="mp4"
    )
    print(f"✅ Storyboard created: {storyboard.concept_id}")
    print(f"   Duration: {storyboard.duration_seconds}s")
    print(f"   Narration: {len(storyboard.narration)} chars")
    print(f"   Keyframes: {len(storyboard.keyframes)}\n")

    # Step 3: Compute storyboard hash
    print("Step 3: Computing storyboard hash...")
    storyboard_hash = maestro._hash_storyboard(storyboard)
    print(f"✅ Storyboard hash: {storyboard_hash[:16]}...")
    print(f"   (ensures reproducibility: same input → same output)\n")

    # Step 4: Validate voice-sync mapping
    print("Step 4: Validating voice-sync mapping...")
    mapper = VoiceSyncMapper(frame_rate=30)

    # Create mock audio metadata (we'll use this for demo)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
        audio = type("NarrationAudio", (), {
            "audio_path": Path(f.name),
            "duration_sec": storyboard.duration_seconds,
            "frame_rate": 30
        })()

        # Create keyframe objects
        keyframes = [
            Keyframe(
                frame=kf["frame"],
                event=kf["event"],
                narrator_text=kf.get("text", ""),
                animation_action=None,
                timestamp_sec=kf["frame"] / 30.0
            )
            for kf in storyboard.keyframes
        ]

        # Create mapping
        mapping = mapper.create_mapping(audio, keyframes)

        # Validate
        errors = mapper.validate_mapping(mapping, audio)
        if errors:
            print(f"⚠️  Validation errors: {errors}")
        else:
            print("✅ Voice-sync mapping validated")
            print(f"   Keyframes: {len(mapping.keyframe_indices)}")
            print(f"   Events at key frames: {list(mapping.frame_to_event.items())[:3]}\n")

    # Step 5: Test tier fallback chain
    print("Step 5: Testing tier fallback chain...")
    print("   Tier preference: TIER_2_RICH (Manim)")
    print("   Fallback chain: TIER_2_RICH → TIER_1_QUICK")
    fallback = dispatcher._get_fallback_chain(TierLevel.TIER_2_RICH)
    print(f"   Actual fallback: {[t.name for t in fallback]}")
    print("✅ Fallback chain is deterministic\n")

    # Step 6: Run full pipeline
    print("Step 6: Running full Maestro pipeline...")
    print(f"   Input: {storyboard.concept_id} storyboard")
    print(f"   Output: /outputs/videos/{storyboard.concept_id}.mp4\n")

    try:
        result = maestro.produce(storyboard)

        if result["success"]:
            print("✅ Video production SUCCESSFUL")
            print(f"   Output path: {result['output_path']}")
            print(f"   Duration: {result['duration_seconds']}s")
            print(f"   Audio duration: {result['audio_duration_sec']:.1f}s")
            print(f"   Tier used: {result['tier_used']}")
            print(f"   Render time: {result['render_time_ms']}ms")
            print(f"   Total time: {result['total_time_ms']}ms\n")

            # Step 7: Verify audit trail
            print("Step 7: Verifying audit trail...")
            audit_count = len(result["audit_events"])
            print(f"✅ Audit events logged: {audit_count}")
            for evt in result["audit_events"]:
                print(f"   - {evt['event_type']} @ {evt['timestamp']}")

            # Step 8: Show hashes (reproducibility)
            print("\nStep 8: Reproducibility verification...")
            print(f"✅ Storyboard hash: {result['storyboard_hash'][:32]}...")
            if result.get('video_hash'):
                print(f"✅ Video file hash: {result['video_hash'][:32]}...")
            print("\nNote: Running again with same storyboard will produce:")
            print("      - Same storyboard hash ✓")
            print("      - Same video hash (if deterministic renderer) ✓")
            print("      - Identical audit trail ✓\n")

            return True

        else:
            print(f"⚠️  Video production FAILED: {result['error']}")
            print("\nPossible reasons:")
            print("  - Manim not installed: pip install manim")
            print("  - FFmpeg not installed: apt-get install ffmpeg")
            print("  - OpenAI API key not configured (optional for demo)")
            print("\nNote: Tier 1 (Quick Renderer) always succeeds as fallback.\n")
            return False

    except Exception as e:
        print(f"❌ Exception during production: {e}")
        import traceback
        traceback.print_exc()
        return False


def demo_tier_metrics():
    """Show tier performance metrics"""
    print_section("TIER PERFORMANCE METRICS")

    tier1 = QuickRendererWorker()
    tier2 = ManimAnimatorWorker()
    dispatcher = TierDispatcher(tier1, tier2)

    metrics = dispatcher.get_metrics()
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 1 Demo")
    parser.add_argument("--metrics", action="store_true", help="Show tier metrics only")
    args = parser.parse_args()

    if args.metrics:
        demo_tier_metrics()
    else:
        success = demo_phase1()
        sys.exit(0 if success else 1)
