"""Alternate TTS worker implementations (class-based, CorvinOS VideoJob protocol).

Merged from CorvinOS core/skills/video_producer/workers/ (Milestone M0
consolidation). These workers speak a different calling convention than the
plugin's live gTTS-based pipeline in skill.py (`job.narration` / `job.job_id`
attributes instead of the plugin's storyboard/scene model) and are not yet
wired into skill.py's orchestrate_video(). They are preserved here as
real OpenAI TTS integrations (tts-1-hd, with espeak-ng / mock fallback
chains) for a future wiring pass.
"""
