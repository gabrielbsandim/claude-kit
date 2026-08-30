#!/usr/bin/env python3
"""The UserPromptSubmit hook speaks once per band and is silent otherwise.

    python3 tests/test-context-nudge.py

Most cases here prove silence, which is the property that decides whether a hook
on every prompt is usable. A line on every message is a line that gets skimmed,
and a hook that fails loudly on a prompt has picked token accounting over the
thing the user asked for.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "context-nudge.py")
SHIM = os.path.join(ROOT, "hooks", "context-nudge.sh")

failures = []
passes = 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
    else:
        failures.append(f"{name}: {detail}")


def transcript(cfg, project, session, reqs):
    d = os.path.join(cfg, "projects", project)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, session + ".jsonl"), "w", encoding="utf-8") as fh:
        for n, u in enumerate(reqs):
            fh.write(json.dumps({
                "type": "assistant", "timestamp": "2026-08-18T00:00:00.000Z",
                "requestId": f"r{n}", "message": {"id": f"m{n}", "usage": u},
            }) + "\n")


def usage(read=0, write=0):
    return {"input_tokens": 0, "output_tokens": 5,
            "cache_creation_input_tokens": write, "cache_read_input_tokens": read}


def fire(cfg, session, extra_env=None, stdin=None, debug=True):
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.pop("KIT_NUDGE_WINDOW", None)
    # Debug on by default here, so a crash surfaces instead of looking like the
    # silence the hook is supposed to produce. The blanket `except Exception` is
    # correct in production and blinding in a test: a mutation that broke the advice
    # lookup for one band passed every case behind it.
    if debug:
        env["KIT_NUDGE_DEBUG"] = "1"
    if extra_env:
        env.update(extra_env)
    payload = stdin if stdin is not None else json.dumps({"session_id": session})
    p = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                       text=True, env=env, cwd=ROOT)
    return p.stdout, p.returncode


def said(out):
    if not out.strip():
        return None
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


root = tempfile.mkdtemp(prefix="kit-nudge-")
try:
    cfg = os.path.join(root, "cfg")

    # 1. HOLD is silent. This is the common case by far and the one that decides
    #    whether the hook is tolerable on every prompt.
    transcript(cfg, "-p", "hold1111", [usage(read=100_000)])
    out, rc = fire(cfg, "hold1111")
    check("1 HOLD says nothing", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")

    # 2. The middle band speaks, once, with the number and the price.
    transcript(cfg, "-p", "mid22222", [usage(read=200_000)])
    out, rc = fire(cfg, "mid22222")
    msg = said(out)
    check("2 the middle band speaks", rc == 0 and msg, f"rc={rc} out={out!r}")
    check("2 it names the verdict", "AT THE NEXT BOUNDARY" in (msg or ""), msg)
    check("2 it carries the percentage", "80% of the window is free" in (msg or ""), msg)
    check("2 it prices the rewrite", "US$ 1.25" in (msg or ""), msg)
    check("2 it says not to compact mid-task", "not mid-task" in (msg or ""), msg)
    check("2 it says the model cannot compact", "cannot" in (msg or ""), msg)
    check("2 it keeps the pause rule", "long pause" in (msg or ""), msg)

    # 3. And is silent the second time, which is the whole point of the state file.
    out2, rc2 = fire(cfg, "mid22222")
    check("3 the same band is silent afterwards", rc2 == 0 and out2.strip() == "", out2)

    # 4. A worse band speaks again, because the advice changed. Ranked, not compared
    #    for equality: an equality check would go quiet forever after the first line.
    transcript(cfg, "-p", "mid22222", [usage(read=700_000)])
    out3, _ = fire(cfg, "mid22222")
    check("4 a worse band speaks again", "NOW" in (said(out3) or ""), out3)
    out4, _ = fire(cfg, "mid22222")
    check("4 and then goes quiet", out4.strip() == "", out4)

    # 5. Going back down is silent. After a compaction the session is small again,
    #    and a line saying so is noise.
    transcript(cfg, "-p", "mid22222", [usage(read=80_000)])
    out5, _ = fire(cfg, "mid22222")
    check("5 dropping back to HOLD is silent", out5.strip() == "", out5)

    # 5b. And climbing back to a band already announced speaks again, because that is
    #     a new crossing. Storing only the loud bands, or comparing by rank alone, left
    #     the stored level stuck high so a session that compacted and refilled was
    #     never warned a second time. Both survived the first suite.
    transcript(cfg, "-p", "mid22222", [usage(read=700_000)])
    out5b, _ = fire(cfg, "mid22222")
    check("5b a re-climb to the same band speaks again", "NOW" in (said(out5b) or ""), out5b)
    out5c, _ = fire(cfg, "mid22222")
    check("5b and then goes quiet again", out5c.strip() == "", out5c)

    # 5c. Every band's advice exists. Reaching a band with no entry raised a KeyError
    #     that the blanket catch turned into silence, so this walks all four.
    for size, want in ((100_000, None), (200_000, "AT THE NEXT BOUNDARY"),
                       (700_000, "NOW"), (950_000, "LATE")):
        sess = "walk%04d" % (size // 1000)
        transcript(cfg, "-p", sess, [usage(read=size)])
        out, rc = fire(cfg, sess)
        check(f"5c band at {size:,} does not crash", rc == 0, f"rc={rc} out={out!r}")
        if want:
            check(f"5c band at {size:,} has advice", want in (said(out) or ""), out)

    # 6. Each band has its own advice, and LATE says the automatic one takes over.
    transcript(cfg, "-p", "late3333", [usage(read=950_000)])
    msg = said(fire(cfg, "late3333")[0])
    check("6 LATE names the automatic compaction", "automatic" in (msg or ""), msg)

    # 7. Every failure is silent and exit 0. A prompt is not the place to fail, so
    #    these are the cases that matter most.
    out, rc = fire(cfg, "nosuchsession")
    check("7 an unknown session is silent", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")
    # A broken payload is silent, and silent because it was handled rather than
    #  because it crashed: debug off would hide the difference, so this asserts both.
    out, rc = fire(cfg, "x", stdin="not json at all")
    check("7 a broken payload is silent", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")
    out, rc = fire(cfg, "x", stdin="not json at all", debug=False)
    check("7 and still silent with the blanket catch", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")
    out, rc = fire(cfg, "x", stdin="")
    check("7 an empty payload is silent", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")
    out, rc = fire(os.path.join(root, "nothing"), "hold1111")
    check("7 an empty config dir is silent", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")

    # 8. The window is overridable, so a Haiku session is not reported as empty.
    transcript(cfg, "-p", "haiku444", [usage(read=180_000)])
    out, _ = fire(cfg, "haiku444")
    check("8 180k is AT THE NEXT BOUNDARY at 1M",
          "AT THE NEXT BOUNDARY" in (said(out) or ""), out)
    out, _ = fire(cfg, "haiku444", extra_env={"KIT_NUDGE_WINDOW": "200000"})
    check("8 and LATE at 200k", "LATE" in (said(out) or ""), out)

    # 9. The shim resolves the newest installed copy rather than a versioned path,
    #    which is the mistake that made the freshness hook go stale.
    shim = open(SHIM, encoding="utf-8").read()
    check("9 the shim sorts and takes the newest", "sort -V | tail -1" in shim, "pinned to one path")
    check("9 the shim exits 0 with nothing installed", "|| exit 0" in shim, "can fail a prompt")
    src = open(HOOK, encoding="utf-8").read()
    check("9 the hook also resolves the newest bin", 'sorted(hits)[-1]' in src, "pinned")

    # 9b. A planted copy in the plugins cache wins over the local clone, and a copy
    #     that answers valid JSON with a field missing is what actually reaches the
    #     blanket catch. Without this case, "silent because handled" and "silent
    #     because it raised" were the same observation, and two mutations that made
    #     the hook raise in production passed every check.
    fake = os.path.join(cfg, "plugins", "cache", "m", "claude-kit", "9.9.9", "bin")
    os.makedirs(fake, exist_ok=True)
    with open(os.path.join(fake, "context"), "w", encoding="utf-8") as fh:
        fh.write('import json\nprint(json.dumps({"verdict": "NOW"}))\n')
    # A session each, because the first call records the band and the second would
    # then exit through the once-per-band gate before ever reaching the failure.
    transcript(cfg, "-p", "fakeaaaa", [usage(read=100_000)])
    transcript(cfg, "-p", "fakebbbb", [usage(read=100_000)])
    out, rc = fire(cfg, "fakeaaaa", debug=False)
    check("9b a malformed answer is swallowed in production", rc == 0 and out.strip() == "",
          f"rc={rc} out={out!r}")
    out, rc = fire(cfg, "fakebbbb", debug=True)
    check("9b and surfaces under KIT_NUDGE_DEBUG", rc != 0, f"rc={rc} out={out!r}")
    shutil.rmtree(os.path.join(cfg, "plugins"), ignore_errors=True)

    # 9c. The banner goes to /dev/tty and never to stdout, because stdout is the
    #     protocol channel: one stray line there and the harness cannot parse the
    #     JSON. The first version only reached the model, so the person who can
    #     actually run /compact never saw it.
    src_hook = open(HOOK, encoding="utf-8").read()
    check("9c the banner writes to the terminal", '"/dev/tty"' in src_hook,
          "no second channel, so only the model is told")
    check("9c and a missing terminal is tolerated", "except OSError" in src_hook,
          "a headless run would fail the prompt")
    transcript(cfg, "-p", "banner11", [usage(read=700_000)])
    out, rc = fire(cfg, "banner11")
    payload = json.loads(out)
    check("9c stdout stays pure JSON", set(payload) == {"hookSpecificOutput"},
          f"extra keys or text on stdout: {out!r}")
    check("9c stdout carries no banner text", "\u00b7" not in out,
          f"the banner leaked into the protocol channel: {out!r}")

    # 10. It never blocks. `decision` and `block` are the fields that would stop a
    #     prompt, and this hook must not learn them.
    check("10 the hook cannot block a prompt",
          '"decision"' not in src and '"block"' not in src, "the hook can refuse a prompt")
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"{passes} passed, {len(failures)} failed")
for line in failures:
    print(f"  FAIL {line}")
sys.exit(1 if failures else 0)
