# Penpot stack (Strang B) - operations runbook

Optional strand. The Video Producer never needs it; without docker or podman it is not offered and normal rendering is unaffected.
Everything below was run on Linux with rootless podman 4.9.3 + podman-compose 1.0.6 unless marked "not tested".
Measurements and the MCP/CVE assessment: `PENPOT-STACK-RESULTS.md`.

All commands: `python3 scripts/penpot_stack/penpot_stack.py [--port N] [--project NAME] [--state-dir DIR] <command>`
(defaults: port 9001, project `penpot`).

## Start, stop, health

| Command | What it does |
|---|---|
| `detect` | prints JSON `{runtime, compose, ...}`; exit 3 + message on stderr when no usable runtime (docker with reachable daemon or podman, plus a compose provider) |
| `up [--wait 300]` | creates secrets on first use, `compose up -d`, waits until the SPA and an anonymous `get-profile` answer; prints seconds; exit 1 if not healthy in time |
| `health` | exit 0 only when frontend and backend answer |
| `status` | compose `ps` |
| `down [--volumes]` | stops and removes the containers; `--volumes` also deletes the data (postgres + assets) |
| `backup --out FILE` / `restore --in FILE` | see below |

Measured: first `up` 35.5 s to healthy (4 images pulled), later 24-50 s. RAM about 3.2 GB (backend JVM about 2.4 GB). Plan for 3 GB.

## Ports and addresses
- The frontend (nginx) is the only published port: `127.0.0.1:<port>` (default 9001). Everything else (backend, exporter, mcp, postgres, valkey, mailpit, admin console) is only on the internal compose network.
- Open the UI as `http://localhost:<port>`, NOT `http://127.0.0.1:<port>`: `PENPOT_PUBLIC_URI` is `http://localhost:<port>` and the SPA's API calls are blocked by CORS from any other origin (measured: blank page with CORS errors).
- The exporter is reached through nginx at `/api/export` (Transit JSON), MCP at `/mcp/stream` and `/mcp/ws`.
- Running two stacks side by side needs a different `--port` and `--project`; the volumes are project-scoped.

## Secrets
- `<state-dir>/<project>.secrets.json`, mode 0600, created on first `up` with random values (`PENPOT_SECRET_KEY`, `PENPOT_DB_PASSWORD`). Default state dir: `$CORVIN_PENPOT_STACK_DIR`, else `$XDG_STATE_HOME/corvin/penpot-stack` (`~/.local/state/...`), on Windows `%LOCALAPPDATA%\corvin\penpot-stack`.
- Nothing secret is committed. `compose.yaml` refuses to start (`${VAR:?}`) without them.
- Keep this file: the secret key signs sessions and tokens; the database password is baked into the postgres volume at first start. Losing the file means restoring into a fresh stack with new secrets (sessions and MCP keys become invalid; data survives).
- podman-compose echoes each container's `-e KEY=VALUE` pairs. The script redacts both secrets from everything it prints (verified: a full backup/down/restore log contained neither value). Do not run `podman-compose` by hand with these variables set and paste its output.
- Windows: the 0600 mode is not enforced by the OS; the file lives in the user's profile.

## Backup (tested)
```
python3 scripts/penpot_stack/penpot_stack.py --port 9101 --project penpotfresh backup --out penpot.dump
```
Runs `pg_dump -Fc` inside the postgres container (custom format, written to `*.part`, renamed on success). Measured: 1.4-1.8 s, 190 KB for a database with one account and one file.
NOT covered: the `penpot_assets` volume (uploaded images, fonts). A file made only of boards, shapes and text (what the render strand uses) lives entirely in postgres. If you upload media, also run `podman volume export <project>_penpot_assets -o assets.tar` (docker has no `volume export`; use a tar helper container). The assets export was not tested.

## Restore (tested)
```
python3 scripts/penpot_stack/penpot_stack.py --port 9101 --project penpotfresh restore --in penpot.dump
```
The command stops frontend, backend, exporter and admin console, starts only postgres, waits for `pg_isready`, runs `pg_restore --clean --if-exists --no-owner`, then starts the full stack and waits for health. It works on a stack that was removed with `down --volumes` (empty volume) and, by design, on a running one. Use the SAME secrets file.

### Evidence of the real run (project `penpotfresh`, port 9101)
1. Created via UI/MCP: account `tester@example.com`, one file with a board, a UI-typed text "Hello UI text" and a rectangle made through MCP `execute_code`. `get-file` read back: revn 3, objects `Board`, `Root Frame`, `mcp-made`, `Hello UI text`.
2. `backup` -> `{"backup": ".../penpot2.dump", "bytes": 190584}`, 1.4 s.
3. `down --volumes` (16.8 s); checked: 0 containers, 0 volumes.
4. `restore` -> healthy after 24.0 s (30.5 s wall clock for the command).
5. Login with the old credentials worked and `get-file` returned revn 3 with the same four objects. (A first run of the same cycle with the previous script version gave the identical result.)

## Update to a following version (NOT tested)
Only the 2.18.3 images were run. The steps below are the expected path from Penpot's own compose model and the measured facts that the backend migrates on start; none of it was executed against a newer tag.
1. Read the Penpot release notes for every version between yours and the target (breaking changes, flags).
2. `backup` (see above) and keep the secrets file.
3. Edit the five `penpotapp/*:2.18.3` tags in `scripts/penpot_stack/compose.yaml` (all five to the same new tag; the tests require them pinned, never `latest`). `postgres:15`, `valkey:8.1`, `mailpit:v1` change only if the release notes say so.
4. `down` (without `--volumes`), then `up`. The backend runs schema migrations on start; watch `health` and the backend logs.
5. Verify: login, open a file, run one export (`/api/export`).
6. Rollback: `down --volumes`, restore the old tag in `compose.yaml`, `restore --in <backup>`. A migrated database cannot be assumed to open with the older backend, so rollback means restoring the pre-update dump, not just changing the tag back. Not tested.
A security update inside the 2.18 line (2.18.x) is expected to be the same procedure with less risk; also untested.

## Failure patterns (measured here or in the PLAN-0952 spike)
| Symptom | Cause | Fix |
|---|---|---|
| `detect` says docker unusable although installed | daemon not running or no socket permission (`permission denied ... docker.sock`) | start the daemon / join the docker group, or install podman; `detect` falls back to podman by itself |
| podman pull fails for `postgres:15` etc. | no unqualified-search registry | images in `compose.yaml` are fully qualified (`docker.io/...`); for podman also `unqualified-search-registries = ["docker.io"]` in `~/.config/containers/registries.conf` helps with other images |
| Blank white/black page, CORS errors in the console | opened via `127.0.0.1` | use `http://localhost:<port>` |
| Port forward vanishes (`connection refused` on the port, containers "Up") | rootless podman's `rootlessport` helper died. Seen on the separate spike stack on :9001, cause not established | `down` + `up` of that project |
| Exporter hangs about 30 s then HTTP 500 | a text shape without `position-data` (shapes built through the RPC API) | build text in the UI, or write `position-data` with the shape; UI-made text always has it (checked) |
| Exporter answers 500 to a normal request | wrong content type: it only speaks Transit JSON (`application/transit+json`, `cmd export-shapes`) | use the Transit body; see the spike scripts |
| Exported SVG has only UUIDs, no names | exporter output | map UUIDs to names via `get-file` |
| SVG references `http://localhost:<port>/fonts/...` | font served by the stack | resolve against the running stack or embed the font |
| MCP tool "No userToken found in session context" | URL without `?userToken=` | use the URL from Integrations -> MCP key |
| MCP tool "No Penpot instance connected for user token" | no browser with the workspace open for that user | open the file in a logged-in browser; the MCP plugin connects itself |
| MCP port not reachable directly | the mcp container publishes no port | go through nginx `/mcp/stream` |
| Leftover network after `down` | podman-compose 1.0.6 does not remove it | `down` in this script removes `<project>_penpot` itself |
| `up` fails with "run penpot_stack.py up" | compose invoked without the secret variables | always go through `penpot_stack.py` |
