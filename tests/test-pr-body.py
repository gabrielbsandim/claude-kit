#!/usr/bin/env python3
"""`kit pr-body` measures the prose a body adds and refuses an essay.

Every case runs the real script in a temp directory, so the template discovery
and the exit codes are the ones a funnel run gets.
"""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PR_BODY = os.path.join(ROOT, "bin", "pr-body")

failures = []
passes = 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
    else:
        failures.append(f"{name}: {detail}")


def run(body, template=None, args=(), cwd=None):
    """Write the body (and optionally a repo template) and run the script."""
    workdir = cwd or tempfile.mkdtemp()
    if template is not None:
        os.makedirs(os.path.join(workdir, ".github"), exist_ok=True)
        with open(
            os.path.join(workdir, ".github", "pull_request_template.md"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(template)
    path = os.path.join(workdir, "body.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    proc = subprocess.run(
        [sys.executable, PR_BODY, path, *args],
        capture_output=True,
        text=True,
        cwd=workdir,
    )
    return proc.stdout + proc.stderr, proc.returncode, workdir


# 1. A short body fits and says so.
out, rc, wd = run("## What and why\n\nOne sentence.\n")
check("1 short body exits 0", rc == 0, f"rc={rc} out={out!r}")
check("1 short body says OK", out.startswith("OK"), out)
shutil.rmtree(wd, ignore_errors=True)

# 2. Over the total budget exits 3, which is what a caller gates on.
out, rc, wd = run("## How\n\n" + ("palavra " * 400) + "\n", args=("--max", "100"))
check("2 over total exits 3", rc == 3, f"rc={rc}")
check("2 over total names the budget", "over the 100 budget by" in out, out)
shutil.rmtree(wd, ignore_errors=True)

# 3. Under the total but with one bloated section still fails, because a body
#    that is short on average and unreadable in one place is unreadable.
body = "## Small\n\nok\n\n## Huge\n\n" + ("x" * 800) + "\n"
out, rc, wd = run(body, args=("--max", "10000", "--section-max", "600"))
check("3 section cap bites on its own", rc == 3, f"rc={rc}")
check("3 section cap names the section", 'section "Huge"' in out, out)
check("3 section cap lists sizes", "by section, largest first" in out, out)
shutil.rmtree(wd, ignore_errors=True)

# 4. A fenced block is evidence, not prose, so a body that is mostly a command
#    still fits. This is the case that makes the budget usable: the rule
#    elsewhere is that a number without its command does not count.
fence = "## Checks\n\n```bash\n" + ("npm run check\n" * 200) + "```\n\nRan it.\n"
out, rc, wd = run(fence, args=("--max", "100"))
check("4 fenced block does not count", rc == 0, f"rc={rc} out={out!r}")
shutil.rmtree(wd, ignore_errors=True)

# 5. An unterminated fence must not swallow the rest of the file. Swallowing
#    fails open in the wrong direction: one stray ``` and every body measures as
#    empty, so the budget stops firing exactly when the body is malformed enough
#    to need it. The first version of this case asserted the swallowing while its
#    comment claimed the opposite, which is the defect it now pins.
out, rc, wd = run("## A\n\n```\ncode\n\n## B\n\n" + ("y" * 800) + "\n", args=("--max", "100"))
check("5 unterminated fence does not swallow the rest", rc == 3, f"rc={rc} out={out!r}")
check("5 the section after the stray fence is measured", 'section "B"' in out, out)
shutil.rmtree(wd, ignore_errors=True)

# 5b. And a closed fence still does not count, so case 5 did not simply break
#     fence handling to make itself pass.
out, rc, wd = run("## A\n\n```\n" + ("z" * 800) + "\n```\n\ndone\n", args=("--max", "100"))
check("5b a closed fence is still evidence", rc == 0, f"rc={rc} out={out!r}")
shutil.rmtree(wd, ignore_errors=True)

# 6. Tables and checkboxes are the template's, not the author's.
tabular = (
    "## Impact\n\n"
    "| Handler | What |\n| --- | --- |\n"
    + "".join(f"| a{i} | {'z' * 60} |\n" for i in range(20))
    + "\n- [x] `npm run check`\n- [ ] Migration replays\n"
)
out, rc, wd = run(tabular, args=("--max", "100"))
check("6 tables and checkboxes are not prose", rc == 0, f"rc={rc} out={out!r}")
shutil.rmtree(wd, ignore_errors=True)

# 7. Filling the template in is not writing it: the template's own lines are
#    subtracted, so a body that is the template plus one sentence measures the
#    sentence.
template = "## What and why\n\n" + ("boilerplate line\n" * 50)
out, rc, wd = run(template + "\nMinha frase.\n", template=template, args=("--max", "100"))
check("7 template lines subtracted", rc == 0, f"rc={rc} out={out!r}")
check("7 reports the template it found", "pull_request_template.md" in out, out)
shutil.rmtree(wd, ignore_errors=True)

# 7b. And the subtraction is not the whole story: the same body without the
#     template on disk is over, which proves case 7 measured the subtraction
#     rather than passing for some other reason.
out, rc, wd = run(template + "\nMinha frase.\n", args=("--max", "100"))
check("7b without the template the same body is over", rc == 3, f"rc={rc} out={out!r}")
shutil.rmtree(wd, ignore_errors=True)

# 8. Headings are labels, not prose. A body of nothing but section titles is
#    empty, and counting them would spend the budget on the template's outline.
out, rc, wd = run("## " + "\n\n## ".join("t" * 70 for _ in range(20)) + "\n", args=("--max", "100"))
check("8 headings are not prose", rc == 0, f"rc={rc} out={out!r}")
shutil.rmtree(wd, ignore_errors=True)

# 9. The environment can move the budget, so a repo that wants a different one
#    does not have to fork the skill.
env = dict(os.environ, KIT_PR_BODY_MAX="20")
workdir = tempfile.mkdtemp()
path = os.path.join(workdir, "body.md")
with open(path, "w", encoding="utf-8") as handle:
    handle.write("## A\n\n" + "z" * 100 + "\n")
proc = subprocess.run(
    [sys.executable, PR_BODY, path], capture_output=True, text=True, cwd=workdir, env=env
)
check("9 KIT_PR_BODY_MAX applies", proc.returncode == 3, f"rc={proc.returncode}")
check("9 KIT_PR_BODY_MAX is the number used", "over the 20 budget" in proc.stdout, proc.stdout)
shutil.rmtree(workdir, ignore_errors=True)

# 10. A missing file is exit 2, not a crash and not a silent pass. A caller that
#     mistypes the path must not read the result as "the body fits".
proc = subprocess.run(
    [sys.executable, PR_BODY, "/nonexistent/body.md"], capture_output=True, text=True
)
check("10 missing file exits 2", proc.returncode == 2, f"rc={proc.returncode}")
check("10 missing file says why", "cannot read" in proc.stderr, proc.stderr)

# 11. An empty body is not an error. Refusing it here would make the check the
#     thing that blocks a draft, and the template being unfilled is a different
#     rule with a different owner.
out, rc, wd = run("")
check("11 empty body exits 0", rc == 0, f"rc={rc} out={out!r}")
shutil.rmtree(wd, ignore_errors=True)

# 12. --quiet prints nothing when it fits, so the funnel can run it inline, and
#     still prints when it does not, because a silent refusal is worse than none.
out, rc, wd = run("## A\n\nshort\n", args=("--quiet",))
check("12 quiet is silent on success", rc == 0 and out == "", f"rc={rc} out={out!r}")
shutil.rmtree(wd, ignore_errors=True)
out, rc, wd = run("## A\n\n" + "z" * 300 + "\n", args=("--quiet", "--max", "100"))
check("12 quiet still speaks on failure", rc == 3 and "TOO LONG" in out, f"rc={rc} out={out!r}")
shutil.rmtree(wd, ignore_errors=True)

# 13. The measurement is the one that produced the number in the skills. Both
#     SKILL.md files quote 11902, and a body of that measured size has to fail
#     the shipped defaults, or the quoted evidence is decoration.
out, rc, wd = run("## Pontos de atenção\n\n" + ("palavra " * 1500) + "\n")
check("13 an essay fails the shipped defaults", rc == 3, f"rc={rc}")
shutil.rmtree(wd, ignore_errors=True)

# 14. The skills quote the same budget the script defaults to. A rule stated in
#     prose and a rule enforced by a command drift the moment nothing compares
#     them, which is the failure this whole file exists to prevent.
src = open(PR_BODY, encoding="utf-8").read()
for skill in ("skills/task/SKILL.md", "skills/ship/SKILL.md"):
    text = open(os.path.join(ROOT, skill), encoding="utf-8").read()
    # The literals, not a substring that any four-digit number would satisfy.
    check(f"14 {skill} quotes the total budget", "2000" in text and "characters of prose" in text,
          "the 2000 literal or the unit is missing")
    check(f"14 {skill} quotes the section cap", "600 per section" in text, "600 per section missing")
    check(f"14 {skill} names the command", "kit pr-body" in text, "kit pr-body missing")
check("14 script default is 2000", "DEFAULT_MAX = 2000" in src, "default moved without the skills")
check("14 script section default is 600", "DEFAULT_SECTION_MAX = 600" in src, "cap moved")

# 15. `kit pr-body` is reachable through the single entry point, because that is
#     the only name the skills use.
kit = open(os.path.join(ROOT, "bin", "kit"), encoding="utf-8").read()
check("15 kit dispatches pr-body", "pr-body)" in kit, "no dispatcher entry")
check("15 kit lists pr-body in usage", "kit pr-body" in kit, "not in the usage header")

print(f"{passes} passed, {len(failures)} failed")
for line in failures:
    print(f"  FAIL {line}")
sys.exit(1 if failures else 0)
