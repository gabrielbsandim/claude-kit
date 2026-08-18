#!/usr/bin/env python3
"""`kit reload` relinks, and says only true things about what a restart buys.

    python3 tests/test-kit-reload.py

There was no test here until 0.7.1, and that is exactly how the message went
wrong and stayed wrong through four releases. It told the reader that the skills
in a running session were stuck on the old copy. Measured on 2026-08-17 in a
session that never restarted, `/claude-kit:task` loaded its SKILL.md from 0.1.0
at 14:11, from 0.1.1 at 19:03 and from 0.3.1 at 23:16, so a skill body is re-read
at each invocation and that half of the message was false.

A false reason to restart is worse than no reason: the reader who follows it once
and sees nothing change stops believing the true reasons next to it.

`claude` is kept off PATH for every case, so the update half never runs and these
cases test the relink and the message, which is all this subcommand owns.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("FAIL  %s\n        %s" % (name, detail))


def installed(cfg, version, name="claude-kit"):
    """A copy where `claude plugin install` puts one, with the real bin/ in it."""
    root = os.path.join(cfg, "plugins", "cache", name, name, version)
    os.makedirs(os.path.join(root, ".claude-plugin"), exist_ok=True)
    with open(os.path.join(root, ".claude-plugin", "plugin.json"), "w") as fh:
        json.dump({"name": name, "version": version}, fh)
    shutil.copytree(os.path.join(KIT, "bin"), os.path.join(root, "bin"), dirs_exist_ok=True)
    return root


def stub_claude(bindir, cfg, installs=None):
    """A fake `claude` whose `plugin update` installs one version, or nothing.

    The long branch of the message only fires when the cache moves under the
    update, so a test that keeps `claude` off PATH can never reach it. That is
    what let the wrong sentence live in the unreachable half.
    """
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, "claude")
    body = "#!/bin/sh\n"
    if installs:
        body += "mkdir -p '%s/.claude-plugin'\n" % installs
        body += "printf '{\"name\":\"claude-kit\",\"version\":\"%s\"}' > '%s/.claude-plugin/plugin.json'\n" % (
            os.path.basename(installs), installs,
        )
        body += "cp -R '%s' '%s/bin'\n" % (os.path.join(KIT, "bin"), installs)
    body += "echo 'stub update done'\n"
    with open(path, "w") as fh:
        fh.write(body)
    os.chmod(path, 0o755)
    return bindir


def reload_from(root, cfg, target, claude_dir=None):
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = cfg
    base = "/usr/bin:/bin"
    env["PATH"] = f"{claude_dir}:{base}" if claude_dir else base
    out = subprocess.run(
        [os.path.join(root, "bin", "kit"), "reload", target],
        capture_output=True, text=True, env=env,
    )
    return out.stdout + out.stderr, out.returncode


root = tempfile.mkdtemp(prefix="kit-reload-")
try:
    cfg = os.path.join(root, "cfgdir")
    target = os.path.join(root, "bin")
    os.makedirs(target, exist_ok=True)

    old = installed(cfg, "0.6.0")
    new_path = os.path.join(cfg, "plugins", "cache", "claude-kit", "claude-kit", "0.7.0")
    claude_dir = stub_claude(os.path.join(root, "stub"), cfg, installs=new_path)

    # 1. It links to the newest installed copy, not to the one it was run from,
    #    and the update landing a new version is what makes the long message fire.
    out, rc = reload_from(old, cfg, target, claude_dir)
    new = new_path
    link = os.path.join(target, "kit")
    check("1 exits 0 without claude on PATH", rc == 0, f"rc={rc} out={out!r}")
    check("1 a link was made", os.path.islink(link) or os.path.exists(link), out)
    check(
        "1 the link points at the newest copy",
        os.path.realpath(link).startswith(os.path.realpath(new)),
        f"link -> {os.path.realpath(link)}, wanted under {new}",
    )
    check("1 it names the version it linked", "0.7.0" in out, out)

    # 2. The message must not claim a skill body needs the restart. This is the
    #    false sentence the suite exists to keep out, so it is asserted as an
    #    absence and phrased the way the old message phrased it.
    lowered = re.sub(r"\s+", " ", out).lower()
    check(
        "2 no claim that skills are stuck until a restart",
        "skills and agents in this session are still" not in lowered,
        f"the retracted sentence is back: {out!r}",
    )
    check(
        "2 it says a skill body is re-read per invocation",
        "re-read from the newest copy at each invocation" in lowered,
        out,
    )

    # 3. And it must still name what the restart is actually for, or correcting
    #    the message turns into deleting it. The header first: without it the three
    #    items below float with nothing saying what they are waiting for, and a
    #    mutation that deleted only the header survived the first version.
    check("3 the restart section is labelled", "waiting on a restart" in lowered, out)
    for real in ("output style", "hooks", "listing"):
        check(f"3 the restart still names {real!r}", real in lowered, out)
    check("3 the unproven half is marked", "inferred" in lowered,
          "the agent-definition claim is asserted rather than marked INFERRED")

    # 4. bin/ is live, which is the other half of the correction: the reader has
    #    to know the command they just installed already works.
    check("4 it says bin is already live", "live already, no restart" in lowered, out)

    # 5. The restart line is the one that works from a shell, and it says where to
    #    run it. `claude -c` alone loses the conversation; running it inside the
    #    session does nothing.
    check("5 the restart line is exec claude -c", "exec claude -c" in out, out)
    check("5 it says where to run it", "in your terminal" in lowered, out)

    # 6. Nothing to do is a different message, and it must not print a restart
    #    line: a restart nobody needs is the same false instruction in reverse.
    quiet = stub_claude(os.path.join(root, "stub2"), cfg)
    out2, rc2 = reload_from(new, cfg, target, quiet)
    check("6 already newest exits 0", rc2 == 0, f"rc={rc2}")
    check("6 already newest says so", "already the newest" in out2, out2)
    check("6 already newest asks for no restart", "exec claude -c" not in out2, out2)

    # 7. No installed copy at all is an error with a reason, not a silent relink
    #    of nothing. A clone with an empty config dir is a real situation.
    empty = os.path.join(root, "emptycfg")
    os.makedirs(empty, exist_ok=True)
    out3, rc3 = reload_from(new, empty, target, quiet)
    check("7 no installed copy is an error", rc3 != 0, f"rc={rc3} out={out3!r}")
    # The sentence, not a word. Asserting "plugins" passed against bash's own
    # `.../plugins/cache/.../kit: line 132: /bin/kit: No such file or directory`,
    # so a mutant that deleted the error entirely still satisfied it.
    check("7 the error is the one die raises", "no installed copy of claude-kit" in out3, out3)
    check("7 it names the directory it looked in", "/plugins" in out3.split("no installed copy")[-1]
          if "no installed copy" in out3 else False, out3)

    # 8. The correction is dated in the source, so the next person to edit this
    #    block finds the measurement instead of re-deriving it.
    src = open(os.path.join(KIT, "bin", "kit"), encoding="utf-8").read()
    check("8 the measurement is recorded next to the code",
          "0.1.1 at 19:03" in src, "the provenance of the correction is gone")
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
