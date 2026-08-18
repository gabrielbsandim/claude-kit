#!/usr/bin/env python3
"""Says once, when the context crosses a band, that it is time to compact.

A `UserPromptSubmit` hook. `kit context` answers the question but only when
somebody remembers to ask it, which is the same failure the plugin-freshness hook
exists to fix: a rule nobody is reminded of is a rule that holds until the day it
matters. This one reminds, and only when the answer changed.

Measured across 16 sessions, 2026-08-11 to 2026-08-18, at API-equivalent rates:
US$ 2442 spent, US$ 393 of it (16%) on requests that read almost nothing from
cache and wrote a whole prefix back, US$ 2.62 each against US$ 0.20 for a normal
request. Compacting does not avoid that rewrite; it makes the one that happens
smaller.

**Once per band, not once per prompt.** A line on every message is a line that
gets skimmed, and the band only worsens a handful of times in a session. HOLD
never speaks at all.

Silent and exit 0 on everything: no `kit` on PATH, no transcript, a parse error,
a timeout. A hook that blocks a prompt to talk about token accounting has picked
the wrong priority.

Env: KIT_NUDGE_WINDOW overrides the assumed window (Haiku is 200k).
"""
import json
import os
import subprocess
import sys

NAME = "kit-context-nudge"
LOUD = ("AT THE NEXT BOUNDARY", "NOW", "LATE")
RANK = {"HOLD": 0, "AT THE NEXT BOUNDARY": 1, "NOW": 2, "LATE": 3}

ADVICE = {
    "AT THE NEXT BOUNDARY": (
        "Compact at the end of this unit of work, not mid-task: dropping detail you "
        "still need costs more in file re-reads than the compaction saves."
    ),
    "NOW": (
        "Compact now, even mid-task. A prefix rewrite at this size is a single "
        "request costing several dollars, and nothing you do decides when it happens."
    ),
    "LATE": (
        "Compact immediately. Past this the automatic compaction fires and picks the "
        "cut point for you, which is never a task boundary."
    ),
}


def to_terminal(line):
    """Put the line where the person who can act will see it.

    `additionalContext` reaches the model and nothing else, so the first version of
    this hook reminded the assistant and left the user out. Only the user can run
    /compact, so a nudge that stops at the model still depends on somebody choosing
    to relay it, which is the remembering this hook exists to remove.

    /dev/tty rather than stdout: stdout is the hook's protocol channel and anything
    printed there that is not the JSON is a parse error. Silent when there is no
    terminal, which is every non-interactive run.
    """
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(line + "\n")
    except OSError:
        pass


def quiet(msg=None, banner=None):
    if banner:
        to_terminal(banner)
    if msg:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": msg}}))
    sys.exit(0)


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def state_path(session):
    d = os.path.join(config_dir(), NAME)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return os.path.join(d, (session or "unknown")[:36] + ".json")


def newest_context_bin():
    """The newest installed copy, so the hook is not pinned to one release.

    Registering a versioned path is what made the freshness hook the next thing to
    go stale, and this hook would inherit that.
    """
    import glob
    hits = glob.glob(os.path.join(config_dir(), "plugins", "cache", "*", "claude-kit", "*", "bin", "context"))
    if hits:
        return sorted(hits)[-1]
    # A clone rather than an install: the hook sits next to bin/ in that case.
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "context")
    return local if os.path.exists(local) else None


def main():
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    session = payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""

    binary = newest_context_bin()
    if not binary:
        quiet()

    cmd = [sys.executable, binary, "--json"]
    window = os.environ.get("KIT_NUDGE_WINDOW")
    if window:
        cmd += ["--window", window]
    if session:
        cmd += ["--session", session[:8]]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        quiet()
    if done.returncode != 0:
        quiet()
    try:
        data = json.loads(done.stdout)
    except ValueError:
        quiet()

    verdict = data.get("verdict")
    path = state_path(session)
    said = ""
    if path and os.path.exists(path):
        try:
            said = json.load(open(path)).get("said", "")
        except (OSError, ValueError):
            said = ""

    # The band is recorded even when it is quiet, which is what lets a re-climb speak.
    # Recording only the loud ones meant that after a compaction dropped the session
    # back to HOLD, climbing to NOW again stayed silent forever, because the stored
    # rank never came down. The comment here used to claim the opposite of the code.
    if path and verdict != said:
        try:
            json.dump({"said": verdict}, open(path, "w"))
        except OSError:
            pass

    if verdict not in LOUD:
        quiet()
    # Once per arrival in a band, not once per prompt.
    if verdict == said:
        quiet()

    quiet(banner=(
        f"kit context: {verdict} \u00b7 {data.get('free_pct')}% of the window free \u00b7 "
        f"a prefix rewrite now would cost about US$ {data.get('one_rewrite_now')} \u00b7 "
        f"{'compact at the end of this unit of work' if verdict == 'AT THE NEXT BOUNDARY' else 'run /compact'}"
    ), msg=(
        f"kit context: {verdict}. {data.get('free_pct')}% of the window is free "
        f"({data.get('used'):,} tokens in context), and one prefix rewrite at this size "
        f"would cost about US$ {data.get('one_rewrite_now')}. {ADVICE[verdict]} "
        f"Tell the user in one clause; do not run /compact yourself, you cannot. "
        f"And whatever the number says, compacting before a long pause is the one that pays most."
    ))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A hook that fails a prompt to talk about token accounting has picked the
        # wrong priority, so every exception is swallowed. KIT_NUDGE_DEBUG re-raises,
        # because with the blanket catch a test cannot tell correct silence from a
        # crash: a mutation that broke the advice lookup went undetected behind it.
        if os.environ.get("KIT_NUDGE_DEBUG"):
            raise
        quiet()
