#!/usr/bin/env python3
"""`kit context` says how full the window is and which of four verdicts applies.

    python3 tests/test-context.py

Every case builds a fake transcript and runs the real script against it, so the
band arithmetic, the session lookup and the fallback are the ones a real run gets.

The bands come out of measurement, not taste: across 16 sessions from 2026-08-11
to 2026-08-18, 16% of an API-equivalent US$ 2442 went to requests that read almost
nothing from cache and wrote a whole prefix back, at US$ 2.62 each against US$ 0.20
for a normal request. The last cases pin the numbers to the skills that quote them.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = os.path.join(ROOT, "bin", "context")

failures = []
passes = 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
    else:
        failures.append(f"{name}: {detail}")


def transcript(cfg, project, session, reqs):
    """A transcript with one assistant row per usage dict given."""
    d = os.path.join(cfg, "projects", project)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, session + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for n, u in enumerate(reqs):
            fh.write(json.dumps({
                "type": "assistant", "timestamp": "2026-08-18T00:%02d:00.000Z" % (n % 60),
                "requestId": f"req_{n}",
                "message": {"id": f"msg_{n}", "model": "claude-opus-5", "usage": u},
            }) + "\n")
    return path


def usage(read=0, write=0, out=10):
    return {
        "input_tokens": 0, "output_tokens": out,
        "cache_creation_input_tokens": write, "cache_read_input_tokens": read,
    }


def run(cfg, *args, cwd=None, session_env=None):
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    if session_env:
        env["CLAUDE_CODE_SESSION_ID"] = session_env
    p = subprocess.run([sys.executable, CTX, *args], capture_output=True, text=True,
                       cwd=cwd or ROOT, env=env)
    return p.stdout + p.stderr, p.returncode


root = tempfile.mkdtemp(prefix="kit-context-")
try:
    cfg = os.path.join(root, "cfg")

    # 1. The four bands, each from the size of the last request's context. `used`
    #    is read + write on that request, because that is what the next one has to
    #    carry and what a rewrite would be charged on.
    for read, want in ((100_000, "HOLD"), (500_000, "AT THE NEXT BOUNDARY"),
                       (700_000, "NOW"), (950_000, "LATE")):
        transcript(cfg, "-p", "s" + str(read), [usage(read=read)])
        out, rc = run(cfg, "--session", "s" + str(read))
        check(f"1 {read:,} in context is {want}", rc == 0 and out.startswith(want),
              f"rc={rc} out={out!r}")

    # 1b. The boundaries themselves, so an off-by-one in the comparison shows up.
    #     600_000 leaves exactly 40% free, which is below the 60 floor and above 35.
    transcript(cfg, "-p", "edge", [usage(read=600_000)])
    out, _ = run(cfg, "--session", "edge")
    check("1b exactly 40% free is the middle band", out.startswith("AT THE NEXT BOUNDARY"), out)
    # 60% exactly is the middle band, not HOLD: the rule reads "above 60%, hold",
    # so the boundary belongs to the side that acts. The first version of this case
    # asserted the opposite and the code was right.
    transcript(cfg, "-p", "edge2", [usage(read=400_000)])
    out, _ = run(cfg, "--session", "edge2")
    check("1b exactly 60% free already acts", out.startswith("AT THE NEXT BOUNDARY"), out)
    # 390_000 leaves 61% free. Not 399_000: the percentage is rounded, so 399_000
    # reports as 60 and lands in the band below. The rounding makes the boundary
    # fuzzy by about 5000 tokens, which is fine for a verdict and worth knowing.
    transcript(cfg, "-p", "edge3", [usage(read=390_000)])
    out, _ = run(cfg, "--session", "edge3")
    check("1b above 60% free is HOLD", out.startswith("HOLD"), out)
    transcript(cfg, "-p", "edge4", [usage(read=399_000)])
    out, _ = run(cfg, "--session", "edge4")
    check("1b the percentage is rounded, not floored", "60% of the window free" in out, out)

    # 2. `used` counts the write half too. A request that wrote 400k and read
    #    nothing is a session with 400k of context, not an empty one, and reading
    #    only cache_read would report it as HOLD while a rewrite costs dollars.
    transcript(cfg, "-p", "wr", [usage(read=0, write=700_000)])
    out, _ = run(cfg, "--session", "wr")
    check("2 the write half counts toward used", out.startswith("NOW"), out)

    # 3. It names what a rewrite would cost right now, which is what makes the
    #    verdict an argument. 700k at US$ 6.25/1M is US$ 4.38, and the figure has to
    #    move with the size: a constant would read as a price and be a decoration.
    check("3 it prices a rewrite at the current size", "US$ 4.38" in out, out)
    transcript(cfg, "-p", "price", [usage(read=200_000)])
    out2, _ = run(cfg, "--session", "price")
    check("3 the price follows the size", "US$ 1.25" in out2, out2)
    out3, _ = run(cfg, "--session", "price", "--json")
    check("3 json carries the same price", json.loads(out3)["one_rewrite_now"] == 1.25, out3)

    # 4. Rewrites already paid for are counted and priced. Two of them here, one
    #    normal request, so the share is most of the spend.
    transcript(cfg, "-p", "hist", [
        usage(read=20_000, write=300_000), usage(read=400_000),
        usage(read=20_000, write=300_000), usage(read=450_000),
    ])
    out, _ = run(cfg, "--session", "hist")
    check("4 it counts the rewrites", "2 rewrites" in out, out)
    check("4 it reports the session spend", "at API rates" in out, out)

    # 4b. Ordinary growth is not a rewrite. A large write next to a large read is
    #     the conversation extending, and calling that a rewrite would make the
    #     number meaningless on every long session.
    transcript(cfg, "-p", "grow", [usage(read=400_000, write=300_000)])
    out, _ = run(cfg, "--session", "grow")
    check("4b growth beside a hit is not a rewrite", "0 rewrites" in out, out)

    # 5. The session comes from the environment, so the answer is about the caller
    #    and not about whichever file was written last. Two sessions exist and the
    #    variable picks the smaller one.
    transcript(cfg, "-p", "aaaa1111", [usage(read=100_000)])
    transcript(cfg, "-p", "bbbb2222", [usage(read=900_000)])
    out, _ = run(cfg, session_env="aaaa1111")
    check("5 CLAUDE_CODE_SESSION_ID selects the session", "aaaa1111" in out and out.startswith("HOLD"), out)
    check("5 it names the session it read", "session aaaa1111" in out, out)

    # 6. A named session is looked for under every project, not only the one the
    #    working directory maps to. Scoping it to the cwd's project answered "no
    #    transcript" for a file that existed.
    transcript(cfg, "-p2", "elsewhere", [usage(read=100_000)])
    out, rc = run(cfg, "--session", "elsewhere")
    check("6 a named session is found in another project", rc == 0, out)

    # 7. An unknown session falls back and says the number is a guess, because a
    #    figure attributed to the wrong session is worse than no figure.
    out, rc = run(cfg, "--session", "nosuch", "--project", os.path.join(cfg, "projects", "-p"))
    check("7 an unknown session still answers", rc == 0, out)
    check("7 and marks the answer as guessed", "guessed" in out, out)

    # 8. Nothing to read is exit 2, not a confident zero. A session with no
    #     requests reported as HOLD would be the tool inventing a verdict.
    empty = os.path.join(cfg, "projects", "-empty")
    os.makedirs(empty, exist_ok=True)
    out, rc = run(cfg, "--project", empty)
    check("8 an empty project exits 2", rc == 2, f"rc={rc} out={out!r}")
    out, rc = run(cfg, "--project", os.path.join(cfg, "projects", "-missing"))
    check("8 a missing project exits 2", rc == 2, f"rc={rc} out={out!r}")
    # 8b. A transcript that exists but records no request is its own case, and the
    #     one the earlier cases could not reach: they had no file at all, so they
    #     exited at the lookup and never touched the guard after reading. A mutant
    #     that replaced that guard with an empty usage dict survived, reporting a
    #     confident 100% free for a session it knew nothing about.
    hollow = os.path.join(cfg, "projects", "-hollow")
    os.makedirs(hollow, exist_ok=True)
    with open(os.path.join(hollow, "nousage.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "timestamp": "2026-08-18T00:00:00.000Z"}) + "\n")
    out, rc = run(cfg, "--project", hollow)
    check("8b a transcript with no requests exits 2", rc == 2, f"rc={rc} out={out!r}")
    check("8b and does not invent a verdict", "HOLD" not in out, out)

    # 9. The window is overridable, because Haiku is 200k and a fixed 1M would
    #    report a full Haiku session as almost empty.
    transcript(cfg, "-p", "haiku", [usage(read=180_000)])
    # 180k of 200k leaves 10% free, which is LATE, not NOW. Asserting NOW here was
    # arithmetic done by hand against a table the script already encodes.
    out, _ = run(cfg, "--session", "haiku", "--window", "200000")
    check("9 --window changes the band", out.startswith("LATE"), out)
    out, _ = run(cfg, "--session", "haiku")
    check("9 the same session is HOLD at 1M", out.startswith("HOLD"), out)
    # 9b. The environment sets it too, so a repo on Haiku does not need the flag on
    #     every call. Only the flag was covered, and a mutant that dropped the env
    #     default survived.
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env["KIT_CONTEXT_WINDOW"] = "200000"
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    p2 = subprocess.run([sys.executable, CTX, "--session", "haiku"],
                        capture_output=True, text=True, cwd=ROOT, env=env)
    check("9b KIT_CONTEXT_WINDOW applies", p2.stdout.startswith("LATE"), p2.stdout + p2.stderr)

    # 10. --json is the shape a caller parses, and it carries the verdict rather
    #     than only the raw numbers.
    out, rc = run(cfg, "--session", "haiku", "--json")
    data = json.loads(out)
    check("10 json carries the verdict", data.get("verdict") == "HOLD", out)
    for key in ("used", "free_pct", "requests", "rewrites", "spent", "one_rewrite_now"):
        check(f"10 json has {key!r}", key in data, out)

    # 11. The pause rule is unconditional, so it is printed in every human answer
    #     rather than only in the urgent bands. It is the one that pays most.
    out, _ = run(cfg, "--session", "haiku")
    check("11 the pause rule is always printed", "before a long pause" in out, out)

    # 12. The skills quote this command and these bands. A rule in prose and a rule
    #     in a command drift the moment nothing compares them.
    for skill in ("skills/task/SKILL.md", "skills/ship/SKILL.md"):
        text = open(os.path.join(ROOT, skill), encoding="utf-8").read()
        check(f"12 {skill} names the command", "kit context" in text, "not referenced")
        for verdict in ("HOLD", "AT THE NEXT BOUNDARY", "NOW", "LATE"):
            check(f"12 {skill} quotes {verdict!r}", verdict in text, "verdict missing")
        check(f"12 {skill} keeps the pause rule", "long pause" in text, "the pause rule is gone")
    src = open(CTX, encoding="utf-8").read()
    check("12 the bands in the script are the documented four",
          all(v in src for v in ("HOLD", "AT THE NEXT BOUNDARY", "NOW", "LATE")), "a band was renamed")
    check("12 the floors are 60, 35 and 15", "(60," in src and "(35," in src and "(15," in src,
          "a floor moved without the skills")
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"{passes} passed, {len(failures)} failed")
for line in failures:
    print(f"  FAIL {line}")
sys.exit(1 if failures else 0)
