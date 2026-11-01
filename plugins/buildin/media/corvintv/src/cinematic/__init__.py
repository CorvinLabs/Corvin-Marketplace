"""CorvinTV cinematic mode: a film of continuous animated acts instead of a sequence of slides.

An act is one shot built from moving figures (``engine/``), narrated in beats; every visual event is tied to the
beat in which the narrator says it. ``direction`` writes and validates the screenplay, ``stage`` builds the
deterministic canvas page and captures frames, ``produce`` runs the whole job (speech, timeline, frames, MP4).
"""
