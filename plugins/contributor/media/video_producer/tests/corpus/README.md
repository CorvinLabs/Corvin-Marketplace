# Corpus baseline (PLAN-0946 R0)

`baseline.json` holds the task texts of the production-readiness corpus and the numbers already measured for the
videos made from them. Only task texts are stored, never audio, video or narration.

- Entries: the seven tenant jobs of 2026-10-09 (`job_13fae6f0 21a8c536 58827bae 66cce242 91bce362 925521fb a6618e32`,
  read from the tenant job store) and the LDD task in German and English
  (`Corvin-Videos/ldd-bei-architekturentscheidungen/source/task.{de,en}.txt`).
- Measured on 2026-10-10 with plugin 1.4.0 (`measured_on`, `plugin_version_measuring`). The seven jobs were re-measured
  with `scripts/measure_engagement.py` (no `--whisper`); the LDD entries carry the stored measurements of their videos
  (plugin 1.3.0 / 1.3.1) including whisper alignment. A `null` is a number nobody has measured; its reason is in `null_reasons`.
- The seven jobs predate the engagement mechanism (ADR-2245): their pooled dead share (57 %) is the starting point, not a target.
- It is a ratchet for the ready-gate (PLAN-0946 R8): the cue-alignment numbers (median 0.73 s / p90 3.37 s DE,
  1.56 s / 6.3 s EN) must not get worse.
