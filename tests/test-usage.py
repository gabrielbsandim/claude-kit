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


def row(request_id, message_id, out_tokens, read=0, model="claude-opus-5",
        day="2026-08-18"):
    message = {"id": message_id, "usage": {
        "input_tokens": 0, "output_tokens": out_tokens,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": read}}
    if model is not None:
        message["model"] = model
    return json.dumps({
        "type": "assistant", "requestId": request_id,
        "timestamp": day + "T12:00:00.000Z", "message": message,
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

# The model decides the rate. One Opus rate over a run where the test writer and the
# reviewer are on Sonnet reports those stages at about 2.5 times what they cost,
# which is the number somebody reads to decide whether moving them was worth doing.
with tempfile.TemporaryDirectory() as cfg:
    build(cfg, SESSION, [row("r1", "m1", 100, model="claude-sonnet-5")], [])
    got = run(cfg, "--session", SESSION)
    check("a Sonnet request is priced as Sonnet", round(got["main"]["cost"], 6),
          round(100 * 10 / 1e6, 6))

with tempfile.TemporaryDirectory() as cfg:
    build(cfg, SESSION, [row("r1", "m1", 100, model=None)], [])
    got = run(cfg, "--session", SESSION)
    check("a request naming no model is priced as Opus", round(got["main"]["cost"], 6),
          round(100 * 25 / 1e6, 6))

# --since and --until cut on the request's own day, not on the file's. A session that
# spans a release is the ordinary case, and a whole-file filter would put all of it
# on one side of the boundary, which is the comparison these flags exist to make.
with tempfile.TemporaryDirectory() as cfg:
    build(cfg, SESSION, [row("r1", "m1", 100, day="2026-08-16"),
                         row("r2", "m2", 700, day="2026-08-18")], [])
    check("--since keeps only the later day",
          run(cfg, "--session", SESSION, "--since", "2026-08-17")["main"]["output"], 700)
    check("--until keeps only the earlier day",
          run(cfg, "--session", SESSION, "--until", "2026-08-17")["main"]["output"], 100)
    check("a window with both ends keeps what is inside it",
          run(cfg, "--session", SESSION, "--since", "2026-08-16",
              "--until", "2026-08-18")["main"]["output"], 800)
    check("no window keeps everything",
          run(cfg, "--session", SESSION)["main"]["output"], 800)
    check("a malformed date is refused rather than ignored",
          run(cfg, "--session", SESSION, "--since", "17/08/2026").get("exit"), 2)

# --by-stage names the stage from the dispatch prompt, because the harness records no
# agent type and names the transcript after an opaque id.
with tempfile.TemporaryDirectory() as cfg:
    project = os.path.join(cfg, "projects", "-tmp-repo")
    subs = os.path.join(project, SESSION, "subagents")
    os.makedirs(subs, exist_ok=True)
    with open(os.path.join(project, SESSION + ".jsonl"), "w") as fh:
        fh.write(row("r0", "m0", 10) + "\n")
    for name, prompt, out_tokens in (
        ("agent-a1", "You are stage 2 of the task funnel. Implement the spec.", 500),
        ("agent-a2", "You are stage 4 (adversarial review) of the task funnel.", 200),
        ("agent-a3", "You are stage 4 of the funnel, the screen lens. Open the routes.", 300),
        ("agent-a4", "Do a thing nobody named.", 40),
    ):
        with open(os.path.join(subs, name + ".jsonl"), "w") as fh:
            fh.write(json.dumps({"type": "user", "isSidechain": True,
                                 "message": {"content": prompt}}) + "\n")
            fh.write(row(name + "-r", name + "-m", out_tokens) + "\n")
    got = run(cfg, "--session", SESSION, "--by-stage")
    stages = got["stages"]
    check("the implementer is named", stages["2 implementer"]["output"], 500)
    check("the reviewer is named", stages["4 reviewer"]["output"], 200)
    # Before the screen lens was checked first, its prompt matched "stage 4" and was
    # billed to the reviewer, which is the stage whose fan-out the rules constrain.
    check("the screen lens is not billed to the reviewer",
          stages["4 screen-lens"]["output"], 300)
    check("an unnameable dispatch is a bucket, not a rounding error",
          stages["other"]["output"], 40)
    check("runs count transcripts, which is executions", stages["2 implementer"]["runs"], 1)
    check("--by-stage covers the whole subagent lane",
          sum(s["output"] for s in stages.values()), got["subagents"]["output"])
    check("without the flag there is no stages key", "stages" in run(cfg, "--session", SESSION),
          False)

print("\n%d ok, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
