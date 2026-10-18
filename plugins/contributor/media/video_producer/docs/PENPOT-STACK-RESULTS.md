# Penpot stack (Strang B) - measured results

Host: Linux 6.17, rootless podman 4.9.3 + podman-compose 1.0.6, Playwright (Python) with Chromium 1243, Penpot 2.18.3.
All runs used a second stack (compose project `penpotfresh`, port 9101) started from `scripts/penpot_stack/compose.yaml`.
Verdict vocabulary: PASSED, FAILED, NOT CHECKED.

## T-0191 - setup on a fresh host (summary; details in the runbook)

| Step | Measured |
|---|---|
| `detect` | docker 29.1.3 is installed but `docker info` fails (permission denied on the socket) - detect correctly falls through to podman 4.9.3 + podman-compose |
| `up` (empty dir, own state dir, port 9101, project `penpotfresh`), first run, 4 of 8 images pulled | 31.2 s until compose returned, 35.5 s until frontend + backend healthy |
| `up`, second and third run (images cached) | 10.8 s compose, 24.0 s to 50.1 s healthy (spread observed: 24, 27, 50 s) |
| RAM, 8 containers, about 2.5 min after start | backend 2.37 GB, frontend 466 MB, exporter 124 MB, rest below 90 MB each; sum about 3.2 GB (spike: 2.97 GB after 10 min) |
| `down --volumes` | about 16 s; afterwards 0 containers, 0 volumes, 0 networks for the project |

Limits of this measurement: image layers were partly cached (earlier 2.18 tags share layers), so a cold-network pull is not measured. Docker was not usable on this host (daemon permission), so the docker path is covered by the fake-executable tests only, not by a real run.

## Re-run 2026-10-18 - runtime override, lifecycle on Podman (T-0191, T-0193)

Host unchanged (Linux, rootless podman 4.9.3, podman-compose 1.0.6). `docker info` now works on this host, so the docker row of the 2026-10-13 table above is out of date: `detect` with `auto` returns docker. Every container below was started under the project `penpotvpe2e` (port 9102), a separate compose project from the stack `penpot` that was already running on this host and was not touched.

| Step (`--runtime podman`, project `penpotvpe2e`) | Result |
|---|---|
| `up --wait 420` (all 8 images local, empty state dir) | healthy after 23.5 s, exit 0, `runtime: podman` |
| marker table written into postgres, then `down` (no `--volumes`) | 0 project containers; the two project volumes stayed |
| `up` again | healthy after 23.2 s; marker row still readable (volume data survived the stop) |
| `backup --out` | 180 174 bytes, `pg_dump -Fc` |
| `down --volumes` | 0 containers, 0 volumes, network removed |
| `restore` straight onto the removed stack (no `up` in between, the documented path) | exit 0, healthy, marker row restored |
| `restore` onto the populated, live database (guard added this run) | exit 2, "already has 61 tables", stack stayed healthy, 8 containers still up |
| `up` with `auto` (no override) | `runtime: podman`, healthy after 37.3 s; no pull was needed |
| final `down --volumes` | 0 project containers, 0 project volumes, state dir (with the secrets file) deleted |

Finding in the same run: `restore` onto a stack that had already started failed with 16 `cannot drop inherited constraint "file_data_NN_pkey"` errors (pg_restore exit 1), and the stack stayed down. The backend creates those partitions on first start. The old runbook sentence "by design, on a running one" was wrong; the script now refuses a populated database before stopping anything (`cmd_restore`, covered by `tests/test_penpot_stack_runtime.py`).

Not measured here: a cold pull from registry-1.docker.io (all images were local); the pull fallback in a live run (it needs an image that is missing from podman); the Docker path with its own images; Windows and macOS (only the platform branches in code, see the runbook's runtime section).

Container count left after this run from the project: 0. The separate `penpot` stack (8 containers, already running when this run began and not started by it) was left running; its owner was not identified.

## T-0192 - checks

### 1. Text created in the Penpot UI exports - PASSED
Playwright (Python, headless Chromium) logged in, opened an empty file in the workspace, drew a board (key B) and a text box (key T), typed "Hello UI text".
`get-file` afterwards showed the text shape WITH `positionData` (so the UI writes the field whose absence hangs the exporter).
Exporter `/api/export` (`export-shapes`, SVG): board 200 in 3.3 s, text shape 200 in 2.7 s. The SVG contains
`<text ...>Hello UI text</text>` (one `<text>` element, no `foreignObject`). The font is referenced as `src: url(http://localhost:9101/fonts/sourcesanspro-regular.woff)`,
so a consumer that renders the SVG offline needs that font or must rewrite the URL.
Caveat: one run, one text, one font.

### 2. MCP `export_shape` / `execute_code` with userToken and plugin - PASSED (with conditions)
Path that worked (all through Playwright, no manual step):
1. Account settings -> Integrations -> MCP Server: switch to Enabled (the switch sits under a cover element; clicking the cover works, clicking the label does not), "Generate MCP key", expiry "Never". The page shows the URL `http://localhost:9101/mcp/stream?userToken=<key>`.
2. Open the file in the workspace with MCP enabled: the toolbar shows an "MCP" indicator and the menu "MCP server" offers "Disconnect", i.e. the plugin connected itself (no manual plugin install).
3. A plain HTTP MCP client (JSON-RPC over `/mcp/stream`, header `mcp-session-id`) then called tools:
   - `execute_code` returned page name and shape list (about 10-20 ms per call; 30 consecutive calls: 30 ok, p50 5 ms, max 8 ms).
   - `execute_code` created a rectangle (`penpot.createRectangle()`); `get-file` via REST afterwards showed it persisted (revn 3).
   - `export_shape` svg of the UI-made text: 2.74 s, SVG identical in structure to the exporter result; png: 2.78 s, base64 PNG returned.
Negative controls measured:
- Without `userToken`: `initialize` is accepted (HTTP 200), tool call fails with "No userToken found in session context. Multi-user mode requires authentication."
- Token valid but browser tab closed: "No Penpot instance connected for user token. Please ensure that Penpot is connected..."
Conditions this implies for Strang B: an open, logged-in browser with the workspace is a hard dependency of `execute_code` and `export_shape`; `execute_code` runs arbitrary JavaScript inside the user's Penpot session (full edit rights of that user). The MCP key has no expiry by default and must be treated like a password; the userToken travels in the URL query.
Caveat: headless Chromium on this host; a second concurrent file/browser, and token revocation, were not tested.

### 3. CVE list for 2.18.3 against primary sources - PASSED as a lookup, with open points
Sources, all fetched 2026-10-13:
- GitHub Security Advisories API of penpot/penpot: `https://api.github.com/repos/penpot/penpot/security-advisories` (24 unique advisories; the listing page https://github.com/penpot/penpot/security/advisories was cross-read).
- NVD API: `https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=penpot` (20 CVEs; all with status Deferred except CVE-2026-26202 Analyzed; NVD carries no 2.18.x configuration for any of them).
- Penpot changelog: https://raw.githubusercontent.com/penpot/penpot/develop/CHANGES.md (entries for 2.18.1, 2.18.2, 2.18.3).

Findings:
- No published GHSA lists a version above 2.18.0 as affected, and every advisory that names a patched version names 2.18.0 or earlier (latest advisory publication date 2026-09-25). So no published advisory in the GitHub list affects 2.18.3.
- The most recent advisories, all published 2026-09-25 (patched 2.18.0): GHSA-4f36-m4hj-cv86 / CVE-2026-105691 critical, OS command injection in the SVG exporter via legacy fill-color (affected "<2.17.1"; the advisory's patched field says "1.17.2", the text says 2.17.2); GHSA-wxgm-8qjw-x445 / CVE-2026-105689 high, SSRF guard bypass in webhooks; CVE-2026-105684..105688, 105690, 105692..105696 medium (share-link scope, team-role escalation, SVG XSS, logout session, chunk upload); GHSA-ch2q-6x56-qg5r and GHSA-852x-m8p9-558v low (MCP WebSocket bridge / REPL on 0.0.0.0, `<= 2.17.2`); NVD CVE-2026-100868 (published 2026-09-27) describes the WebSocket bridge item.
- Earlier, patched before 2.18: CVE-2026-26202 (file read, 2.13.2), CVE-2026-44986 (account takeover, 2.14.5), CVE-2026-45805 (MCP REPL RCE, 2.15.0), CVE-2026-45806 (SSRF, 2.15.0), CVE-2026-47665 / -47666 (XSS, 2.15.3).
- 2.18.2 and 2.18.3 changelog entries are bug fixes of SVG sanitising on upload/binfile import and team-member file access; no CVE id is attached to them in the sources read.
- CLOSED (2026-10-14): CVE-2026-17613 (`import-binfile` lacks authorization on `file-id`, authenticated overwrite of any file; published 2026-08-05). OSV and the CVE record list the affected range as up to and including 2.17.0 (`last_affected: 2.17.0`); SentinelOne says fixed in 2.17.0. The sources disagree only about 2.17.0 itself; the pinned 2.18.3 is newer than both readings, so it is not affected. Not checked: the vendor patch commit itself. The stack is single-operator, so the authenticated-user precondition also narrows the exposure. The 2.18.3 changelog mentions a different binfile-import fix (unsanitized SVG).
- Not done: scanning the 2.18.3 images (no scanner run), reading each advisory's full text beyond summary and version ranges.
Exposure in this setup: frontend published on 127.0.0.1 only; MCP/exporter/postgres/valkey publish nothing; the mailpit UI is not published; telemetry is disabled in the compose file. Registration is open for anyone who can reach the port, so the loopback binding is the access control.

### Recommendation: is MCP part of Strang B?
No for the first cut of Strang B; the exporter path is enough and is what the render pipeline needs.
Reasons: (a) every MCP tool that does real work depends on an open, logged-in browser tab, which a headless render pipeline would have to drive itself (Playwright worked here, but it adds a Chromium dependency and a failure mode); (b) `execute_code` is arbitrary code in the user's session, and MCP has the worst advisory history of the stack (three MCP advisories in 2026 incl. one RCE); (c) the static-asset need (SVG of a board) is already met by `/api/export` in 2.7-3.3 s without a browser.
Make MCP an explicit opt-in later (agent-driven design edits), behind its own gate, loopback only, with the key in the 0600 secrets area. The check above shows it is technically feasible.

## Gate review 2026-10-18 - per task (E-030, measured; not an operator verdict)

Measured by an agent on 2026-10-18 against the wording of each task's Definition of Done in the knowledge base.
The spike numbers are from NOTE-0004 (raw data in `claude-playground/penpot-spike-2026-10-18/`); code claims were
checked with the tests on `origin/main` (`test_penpot_import`, `test_penpot_gradients`, `test_penpot_stack*`,
`test_penpot_to_json_cli`: 122 passed, 1 opt-in skipped). Verdicts: MET, PARTIAL, NOT MET, NOT CHECKED.

| Task | Verdict | Measured |
|---|---|---|
| T-0182 Docker deploy and footprint | NOT MET | Stack healthy in 23.5 s (podman). Idle RAM 3.27 GiB (about 3.4 GB) against < 2 GB; idle CPU 15-17 % against < 5 %; DB 12 MB, volumes 51 MB (< 5 GB, met). Inspect tab and SVG/JSON buttons in the UI not checked. |
| T-0183 MCP server and WebSocket | NOT MET | HTTP stream: 50/50 calls OK, max 2 ms. WebSocket without token closes with 1008 (expected). Authenticated WebSocket handshake, 30 s hold, 10 WebSocket requests and the audit events not measured. MCP is outside the first cut (ADR-2257). |
| T-0184 Test template | PARTIAL | Built through the API: 1920x1080 board, 200x200 logo at (100,100) #0066CC, two texts 48 / 32 in #333333, five library colours. Font is sourcesanspro (Penpot default), not Arial or a system default. UI visibility, centring and the Inspect tab not checked. |
| T-0185 SVG export and JSON converter | PARTIAL | 10/10 exports HTTP 200 and well-formed, identical size. The spike converter dropped 4 rectangles (NOT MET for "no data loss"); the hardened module in `penpot_import.py` reads the real fixture with no drops (`test_real_penpot_export_is_read_completely`). Font assertion not met (sourcesanspro). |
| T-0186 Gate G0 | NOT MET (strict reading) | K1 runbook and start time met (runbook 94 lines; the lifecycle is `penpot_stack.py`, there is no `setup.sh`). K2 HTTP 50/50 met, WebSocket not measured. K3 10/10 met. K4 NOT MET (RAM and CPU as above). K5 PASSED as a lookup (see CVE section above); image scan not run. Under the DoD rule "any criterion FAIL -> NO-GO" the measured verdict is NO-GO on K4. The DoD says the closing verdict belongs to the operator; it is not recorded here as a decision. |
| T-0187 Import module hardening | MET | `penpot_import.py` on `origin/main` (commit f2f953f) refuses DOCTYPE/ENTITY, size, nesting, external references, and names unknown Penpot structure. Hostile-input fixtures green. Console-level E2E was not re-run on `origin/main` (see blocker below). |
| T-0188 Shape model to HTML/SVG renderer | PARTIAL | Renderer emits only the closed model; Chromium test passes, but the pixel comparison excludes the two text boxes (font fallback). "Connection to expressive scenes (PLAN-0947)" is not evidenced: Penpot output reaches the `still` asset path only. |
| T-0189 Import path in skill and console | PARTIAL | Console upload (`/assets/import-penpot`) and style import are wired; audit events `video_producer.asset_uploaded` and `video_producer.style_imported` are registered in severity and allowlist; the E2E checks the hash chain. Skill invocation is not wired: `src/skill.py` has no Penpot reference. |
| T-0193 Operations runbook | MET | `docs/PENPOT-STACK-RUNBOOK.md`: backup and restore run for real (evidence section, 2026-10-18), update path described and marked NOT tested. |

Blocker recorded for T-0187: the console loads the plugin from the sibling checkout
`Corvin-Marketplace/` (`routes/video_producer_api.py::_plugin_locations`), and that checkout's local `main` predates
f2f953f. The plain-SVG refusal test therefore fails when run against that checkout, and passes with the
`origin/main` code.
