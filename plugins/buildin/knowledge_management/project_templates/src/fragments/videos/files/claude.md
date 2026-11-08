## Videos

- Every video exists in two languages, German and English, as two runs (the English version is its own narration and TTS run, not translated subtitles). Check numbers across both.
- A video folder holds `<name>.de.mp4`, `<name>.en.mp4`, `sources.md` (copy `videos/TEMPLATE-sources.md`), `source/` (the GENERATIVE code and every input: render script with `__file__`-relative paths, narration, specs) and `build/` (regenerated, not source).
- Move the generative code with the video; a bare MP4 is not reproducible. Drop abandoned scripts.
- The CorvinOS symbol appears large at the start of every video (the renderer enforces it; set nothing per video).
- Acceptance: ffprobe values, loudness about -16 LUFS with no silent segment, frames sampled and looked at, total duration equals the sum of the segments (under 1 s tolerance).
- Do not claim a video is production ready without the measured result that says so.
