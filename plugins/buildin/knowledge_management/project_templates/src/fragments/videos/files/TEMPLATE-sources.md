# sources.md - <video name>

Rules: invent nothing - a missing fact reads `nicht ermittelbar: <reason>`. Paths are relative to the video folder or repo paths. No e-mail addresses, credentials or tokens.
The eight sections below keep their names (they are shared with every other video folder).

## Videoeigenschaften
One line per MP4: file, duration in seconds, resolution, frame rate, video codec, audio (codec, sample rate, channels), size in MB. Values from `ffprobe`.

## Inhalt
Chapters or segments, language of this version, audience, core message. From the narration and storyboard.

## Reproduktion
Numbered steps with the commands that exist (render script, parameters). Dependencies (ffmpeg, Python packages, browser, TTS service).

## Konfiguration
Voice, speech provider, models, resolution, loudness, render options. Only what is in code or config files.

## Pipeline
The stages in order (script, worker, tool), with paths.

## Quellen im Codebase
Repo paths of the sources (code, data, slides, narration) that produce the video.

## Bekannte Einschränkungen
Honest limits: a missing language, an unchecked audio track, open points, outdated parts.

## Verwandte ADRs/Konzepte
Only ids that exist in the knowledge base. Otherwise `keine`.
