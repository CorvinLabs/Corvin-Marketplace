# release_lint fixtures (T-0094)

Each directory is a minimal plugin (`plugin/`) plus its marketplace index (`index/plugins.json`) that
reproduces ONE historical release defect of the Video Producer (ADR-2247, "Measured state" C).
`EXPECTED` names the check that must catch it; `clean` is the negative control and must pass.

| case | defect | where it happened |
|---|---|---|
| `version_index` | plugin.json 1.1.0, all four index blocks 1.0.0 | 1.1.0 listing, fixed in 1.2.0 (7f85179) |
| `version_provider` | plugin.yaml and provider.py 1.0.0 inside the 1.2.0 release | fixed in 5efb2e7 |
| `placeholder` | `RESULTS_PLACEHOLDER` in the release notes | 1.3.0 notes (ADR-2247) |
| `missing_test` | the notes name `test_api_routes.py::test_video_job_end_to_end`; the file existed, the test never did | 1.1.0 notes, removed in 301ba23 |

These are fixtures, not tests: `tests/conftest.py` keeps pytest from collecting the `test_*.py` files in them.
