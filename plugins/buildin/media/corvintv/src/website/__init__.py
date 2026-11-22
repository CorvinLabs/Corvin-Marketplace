"""Website tour (CONCEPT-0139, ADR-2336): a narrated MP4 and a shareable page from a website.

The third CorvinTV job mode (``config["mode"] == "website"``), chosen through the video template ``website``.
Modules, each with one job: ``camera`` (one smooth scroll path), ``timeline`` (spoken lengths -> scene times),
``plan`` (tour schema, validator, model prompt), ``page`` (the source: URL through the capture proxy or a local
folder, plus the outline), ``effects`` (page-side effects), ``render`` (frames), ``audio`` (per-language mix),
``bundle`` (the page to put online), ``produce`` (the job).
"""
