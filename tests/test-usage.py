#!/usr/bin/env python3
"""Proves `kit usage` finds the subagent lane and counts each request once.

    python3 tests/test-usage.py

The lane split is the whole point, and it is the part a naive reader gets wrong:
a subagent's usage is never written into its parent transcript, it lives under
`<project>/<session>/subagents/`. A version that globs only `projects/*/*.jsonl`
reports every subagent as free, which is what the first measurement of this
machine did before the directory was found.
"""
import json
import os
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE = os.path.join(KIT, "bin", "usage")
PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("ok    %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s\n        got  %r\n        want %r" % (name, got, want))


def row(request_id, message_id, out_tokens, read=0):
    return json.dumps({
        "type": "assistant", "requestId": request_id,
        "message": {"id": message_id, "usage": {
            "input_tokens": 0, "output_tokens": out_tokens,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": read}},
    })


def build(cfg, session, main_rows, sub_rows):
    project = os.path.join(cfg, "projects", "-tmp-repo")
    os.makedirs(os.path.join(project, session, "subagents"), exist_ok=True)
    with open(os.path.join(project, session + ".jsonl"), "w") as fh:
        fh.write("\n".join(main_rows) + "\n")
    if sub_rows:
        with open(os.path.join(project, session, "subagents", "agent-a1.jsonl"), "w") as fh:
            fh.write("\n".join(sub_rows) + "\n")


def run(cfg, *args):
    out = subprocess.run([sys.executable, USAGE, "--json", *args], capture_output=True,
                         text=True, env=dict(os.environ, CLAUDE_CONFIG_DIR=cfg,
                                             CLAUDE_CODE_SESSION_ID=""))
    if out.returncode != 0:
        return {"exit": out.returncode, "stdout": out.stdout.strip()}
    return json.loads(out.stdout)


SESSION = "11111111-2222-3333-4444-555555555555"

with tempfile.TemporaryDirectory() as cfg:
    build(cfg, SESSION,
          [row("r1", "m1", 100), row("r2", "m2", 200)],
          [row("r3", "m3", 700), row("r4", "m4", 300)])
    got = run(cfg, "--session", SESSION)
    check("main lane counted", got["main"]["output"], 300)
    check("subagent lane found under subagents/", got["subagents"]["output"], 1000)
    check("subagent transcripts counted", got["subagent_transcripts"], 1)
    check("share is of tokens, not of requests", got["subagent_share_pct"], 76.9)

with tempfile.TemporaryDirectory() as cfg:
    # The same request written twice is one request, which is what read_usage is for.
    build(cfg, SESSION, [row("r1", "m1", 100), row("r1", "m1", 100)], [])
    got = run(cfg, "--session", SESSION)
    check("a repeated request is counted once", got["main"]["requests"], 1)

with tempfile.TemporaryDirectory() as cfg:
    build(cfg, SESSION, [row("r1", "m1", 100)], [])
    got = run(cfg, "--session", SESSION)
    check("no subagents is zero, not a crash", got["subagents"]["tokens"], 0)
    check("cost uses the rates from bin/context", round(got["main"]["cost"], 6), round(100 * 25 / 1e6, 6))

with tempfile.TemporaryDirectory() as cfg:
    os.makedirs(os.path.join(cfg, "projects"), exist_ok=True)
    got = run(cfg, "--session", "99999999-0000-0000-0000-000000000000")
    check("a session with no transcript exits 1 and says so", got.get("exit"), 1)

print("\n%d ok, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
