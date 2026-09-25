#!/usr/bin/env python3
"""Proves the two new-code gates judge what a branch adds and nothing it inherited.

    python3 tests/test-new-code.py

`kit comments` pairs every "must refuse" with a "must pass", because a comment gate
with a false positive is a gate somebody deletes on the first Friday. `kit ratchet`
runs against a fake ESLint that reads markers out of the file, so the matching is
tested without a node_modules, and the fake says exactly what the real one says
about a metric: the measurement is inside the message.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "scripts", "kit")
PASS, FAIL = 0, []

FAKE_ESLINT = r'''#!/usr/bin/env python3
import json, re, sys
args = sys.argv[1:]
if "--version" in args:
    print("v8.57.1"); sys.exit(0)
def messages(text):
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if "DEPTH" in line:
            out.append({"ruleId": "max-depth", "severity": 2, "line": n,
                        "message": "Blocks are nested too deeply (3). Maximum allowed is 2."})
        hit = re.search(r"COMPLEX:(\d+)", line)
        if hit:
            out.append({"ruleId": "complexity", "severity": 2, "line": n,
                        "message": "Function 'f' has a complexity of %s. Maximum allowed is 10." % hit.group(1)})
        if "WARN" in line:
            out.append({"ruleId": "max-lines-per-function", "severity": 1, "line": n,
                        "message": "Function 'g' has too many lines (70). Maximum allowed is 60."})
    return out
if "--stdin" in args:
    name = args[args.index("--stdin-filename") + 1]
    print(json.dumps([{"filePath": name, "messages": messages(sys.stdin.read())}])); sys.exit(0)
skip = {"-c", "-f"}
files, i = [], 0
while i < len(args):
    if args[i] in skip:
        i += 2; continue
    if args[i].startswith("--"):
        i += 1; continue
    files.append(args[i]); i += 1
import os
print(json.dumps([{"filePath": os.path.abspath(f), "messages": messages(open(f).read())} for f in files]))
'''


def check(name, ok, detail=""):
    global PASS
    if ok:
        PASS += 1
    else:
        FAIL.append(f"{name}: {detail}")


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as handle:
        handle.write(text)


def kit(root, *args):
    out = subprocess.run([KIT, *args], cwd=root, capture_output=True, text=True)
    return out.returncode, out.stdout + out.stderr


def repo(files, config=None):
    root = tempfile.mkdtemp(prefix="kit-newcode-")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    write(root, ".claude/funnel.config.json", json.dumps(config or {"base": "main"}))
    write(root, "keep.txt", "x\n")
    for path, text in files.items():
        write(root, path, text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def comments_case(name, added, want, base="", path="src/a.ts", config=None, commit=True):
    root = repo({path: base} if base else {}, config)
    try:
        write(root, path, base + added)
        if commit:
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "change")
        code, out = kit(root, "comments")
        check(name, code == want, f"exit {code}, want {want}\n{out}")
        return out
    finally:
        shutil.rmtree(root, ignore_errors=True)


# The cap is lines of text, so a JSDoc's delimiters are free and its third line is not.
comments_case("a two-line comment passes", "// why one\n// why two\nconst a = 1\n", 0)
comments_case("a three-line comment fails", "// one\n// two\n// three\nconst a = 1\n", 1)
comments_case("a JSDoc with two lines of text passes",
              "/**\n * why one\n * why two\n */\nconst a = 1\n", 0)
comments_case("a JSDoc with three lines of text fails",
              "/**\n * one\n * two\n * three\n */\nconst a = 1\n", 1)
comments_case("two short comments apart are two runs",
              "// one\n// two\nconst a = 1\n// three\nconst b = 2\n", 0)
comments_case("a trailing comment does not join the run above it",
              "// one\n// two\nconst a = 1 // three\n", 0)

# Only what the branch adds. A legacy essay above the change is not this change's.
comments_case("an inherited long comment is not the branch's",
              "const b = 2\n", 0, base="// one\n// two\n// three\n// four\nconst a = 1\n")
comments_case("an uncommitted new file is judged too",
              "// one\n// two\n// three\n", 1, path="src/new.ts", commit=False)

# What belongs in the tracker and the commit.
comments_case("a ticket key fails", "// keeps ABC-123 from coming back\nconst a = 1\n", 1)
comments_case("an encoding name is not a ticket", "// the body is UTF-8, never latin1\nconst a = 1\n", 0)
comments_case("a date fails", "// measured on 2026-09-25\nconst a = 1\n", 1)
comments_case("a count fails", "// 17 of 17 were over budget\nconst a = 1\n", 1)
comments_case("a pull request number fails", "// see #321 for the reason\nconst a = 1\n", 1)
comments_case("a URL is code, not a comment", "const u = 'https://example.com//x'\n", 0)
comments_case("a directive is not prose",
              "// eslint-disable-next-line no-console\n// one\n// two\nconsole.log(1)\n", 0)
comments_case("a Usage block ends the count",
              "/**\n * Backfills the rows.\n * Dry run by default.\n *\n * Usage:\n *   run it\n *   --apply\n */\n", 0)
comments_case("a repo's own ticket pattern applies, in any case",
              "// written for med-2063\nconst a = 1\n", 1,
              config={"base": "main", "comments": {"ticket": "(?i)\\bmed-\\d+\\b"}})

# Other comment syntaxes.
comments_case("three hash comments fail in Python", "# one\n# two\n# three\nx = 1\n", 1, path="a.py")
comments_case("a shebang is not a comment", "#!/usr/bin/env python3\n# one\n# two\nx = 1\n", 0, path="a.py")
comments_case("a colour in a string is not a comment", "x = '#fff'\n", 0, path="a.py")
comments_case("three SQL comments fail", "-- one\n-- two\n-- three\nselect 1;\n", 1, path="m.sql")
out = comments_case("a Markdown file is not code", "one\ntwo\nthree\nfour\n", 0, path="README.md")


def ratchet_case(name, base_files, head_files, want, rename=None, untracked=False, expect=None):
    root = repo(base_files)
    try:
        fake = os.path.join(root, ".git", "fake-eslint")
        with open(fake, "w") as handle:
            handle.write(FAKE_ESLINT)
        os.chmod(fake, 0o755)
        write(root, ".claude/lite.json", "{}")
        if rename:
            git(root, "mv", *rename)
        for path, text in head_files.items():
            write(root, path, text)
        if not untracked:
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "change")
        code, out = kit(root, "ratchet", "--eslint", fake, "--config", ".claude/lite.json")
        check(name, code == want, f"exit {code}, want {want}\n{out}")
        if expect:
            check(name + ", and says so", expect in out, out)
    finally:
        shutil.rmtree(root, ignore_errors=True)


ratchet_case("an added violation fails", {"src/a.ts": "DEPTH\n"}, {"src/a.ts": "DEPTH\nx\nDEPTH\n"}, 1,
             expect="1 new error(s)")
ratchet_case("a moved violation is inherited", {"src/a.ts": "x\nDEPTH\n"}, {"src/a.ts": "DEPTH\nx\ny\n"}, 0,
             expect="1 inherited")
ratchet_case("a metric that improved is inherited",
             {"src/a.ts": "COMPLEX:12\n"}, {"src/a.ts": "COMPLEX:11\n"}, 0)
ratchet_case("a metric that got worse is new",
             {"src/a.ts": "COMPLEX:12\n"}, {"src/a.ts": "COMPLEX:13\n"}, 1)
ratchet_case("a new warning is reported and does not fail",
             {"src/a.ts": "x\n"}, {"src/a.ts": "WARN\n"}, 0, expect="1 new warning(s)")
ratchet_case("an untracked new file is judged",
             {}, {"src/new.ts": "DEPTH\n"}, 1, untracked=True)
ratchet_case("a renamed file keeps what it inherited",
             {"src/a.ts": "DEPTH\n"}, {}, 0, rename=("src/a.ts", "src/b.ts"))
ratchet_case("a file outside the extensions is skipped",
             {"a.md": "DEPTH\n"}, {"a.md": "DEPTH\nDEPTH\n"}, 0, expect="no changed file")

print(f"{PASS} passed, {len(FAIL)} failed")
for line in FAIL:
    print(f"  FAIL {line}")
sys.exit(1 if FAIL else 0)
