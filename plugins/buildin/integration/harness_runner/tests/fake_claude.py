#!/usr/bin/env python3
"""Stand-in for the `claude` CLI (real subprocess, selected through CORVIN_CLAUDE_BIN).

Answers BOTH calls the runner provokes: the worker turn (stream-json on stdin/stdout) and the L44
Tier-1 classifier (`claude -p --max-turns 1 --output-format json <prompt>`), so the real house-rules
code runs. FAKE_CLAUDE_DUMP: a directory; every spawn writes <pid>.json (argv, env, cmdline).
FAKE_CLAUDE_MODE: ok | hang.  FAKE_CLAUDE_VIOLATE: a word that makes the classifier flag a rule.
"""
import json, os, re, sys, time

argv = sys.argv[1:]
dump = os.environ.get("FAKE_CLAUDE_DUMP")
if dump:
    os.makedirs(dump, exist_ok=True)
    with open(os.path.join(dump, f"{os.getpid()}.json"), "w") as fh:
        json.dump({"argv": argv, "env": dict(os.environ), "cwd": os.getcwd(),
                   "cmdline": open(f"/proc/{os.getpid()}/cmdline").read().split("\0"),
                   "sysprompt": (open(argv[argv.index("--append-system-prompt-file") + 1]).read()
                                 if "--append-system-prompt-file" in argv else ""),
                   "kind": "classifier" if "--max-turns" in argv else "worker"}, fh)

if "--max-turns" in argv:  # L44 classifier
    prompt = argv[-1]
    rid, conf = "", 0.97
    word = os.environ.get("FAKE_CLAUDE_VIOLATE")
    if word and word in prompt.split("<user_task>")[-1]:
        m = re.search(r"- id=(\S+) \|", prompt)
        rid = m.group(1) if m else "x"
    print(json.dumps({"type": "result", "is_error": False,
                      "result": json.dumps({"violated_rule_id": rid, "confidence": conf, "reason": "fake"})}))
    sys.exit(0)

first = sys.stdin.readline()
try:
    msg = json.loads(first)
    text = msg["message"]["content"]
    text = text if isinstance(text, str) else "".join(b.get("text", "") for b in text)
except Exception:
    text = first
if dump:
    with open(os.path.join(dump, f"{os.getpid()}.prompt.txt"), "w") as fh:
        fh.write(text)

def out(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()

out({"type": "system", "subtype": "init", "session_id": "fake-sess", "model": "fake-model"})
if os.environ.get("FAKE_CLAUDE_MODE") == "hang":
    while True:
        time.sleep(30)
for d in re.findall(r"--add-dir\s+(\S+)", " ".join(argv)) or []:
    pass
wd = argv[argv.index("--add-dir") + 1] if "--add-dir" in argv else "."
with open(os.path.join(wd, "fake_output.txt"), "w") as fh:
    fh.write("written by fake claude\n")
cfg = os.environ.get("CLAUDE_CONFIG_DIR")
if cfg:
    os.makedirs(os.path.join(cfg, "projects", "x"), exist_ok=True)
    with open(os.path.join(cfg, "projects", "x", "fake-sess.jsonl"), "w") as fh:
        fh.write(json.dumps({"type": "user", "message": {"content": text}}) + "\n")
out({"type": "assistant", "message": {"content": [{"type": "text", "text": "done: fake answer"}]}})
out({"type": "result", "subtype": "success", "is_error": False, "result": "done: fake answer",
     "session_id": "fake-sess", "total_cost_usd": 0.0123, "duration_ms": 5,
     "usage": {"input_tokens": 11, "output_tokens": 7, "cache_read_input_tokens": 3,
               "cache_creation_input_tokens": 2}})
