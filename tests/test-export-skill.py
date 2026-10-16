#!/usr/bin/env python3
"""`kit export-skill` packages a skill that runs outside this plugin, or refuses.

The real skills are exported into a temp directory, and the refusals run
against a fake plugin root, so the exit codes are the ones a caller gets.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

try:
    import yaml
except ImportError:
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT = os.path.join(ROOT, "scripts", "export-skill")
PORTABLE = ("investigate", "note")

failures = []
passes = 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
    else:
        failures.append(f"{name}: {detail}")


def run(*args):
    proc = subprocess.run([sys.executable, EXPORT, *args], capture_output=True, text=True)
    return proc.stdout + proc.stderr, proc.returncode


def frontmatter(path):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    return text.split("---\n")[1]


def fake_root(skill_text, manifest=None):
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "skills", "demo"))
    os.makedirs(os.path.join(root, ".claude-plugin"))
    with open(os.path.join(root, ".claude-plugin", "plugin.json"), "w") as handle:
        json.dump({"version": "1.2.3", "license": "MIT", "homepage": "https://example.com"}, handle)
    with open(os.path.join(root, "skills", "demo", "SKILL.md"), "w") as handle:
        handle.write(skill_text)
    if manifest is not None:
        os.makedirs(os.path.join(root, "export"))
        with open(os.path.join(root, "export", "demo.json"), "w") as handle:
            json.dump(manifest, handle)
    return root


with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as handle:
    VERSION = json.load(handle)["version"]

# 1. The portable skills export, carry license and version, and parse strictly.
out = tempfile.mkdtemp()
for name in PORTABLE:
    text, rc = run(name, "--out", out, "--zip")
    check(f"1 {name} exits 0", rc == 0, text)
    skill = os.path.join(out, name, "SKILL.md")
    check(f"1 {name} has LICENSE", os.path.isfile(os.path.join(out, name, "LICENSE")))
    with zipfile.ZipFile(os.path.join(out, f"{name}.zip")) as archive:
        check(f"1 {name} zip holds the skill", f"{name}/SKILL.md" in archive.namelist(), archive.namelist())
    if yaml is None:
        continue
    meta = yaml.safe_load(frontmatter(skill))
    check(f"1 {name} license", meta.get("license") == "MIT", meta)
    check(f"1 {name} version", meta.get("metadata", {}).get("version") == VERSION, meta)
    check(f"1 {name} compatibility", bool(meta.get("compatibility")), meta)
shutil.rmtree(out, ignore_errors=True)

# 2. A skill that needs the funnel is refused with exit 3 and leaves nothing behind.
out = tempfile.mkdtemp()
text, rc = run("task", "--out", out)
check("2 task exits 3", rc == 3, f"rc={rc}")
check("2 task names a kit subcommand", "a kit subcommand" in text, text[:300])
check("2 task leaves no package", not os.path.exists(os.path.join(out, "task")))
shutil.rmtree(out, ignore_errors=True)

# 3. A manifest whose text drifted from the skill exits 2 and names the text.
root = fake_root(
    "---\nname: demo\ndescription: A demo.\n---\n\nBody.\n",
    {"replace": [{"from": "gone sentence", "to": "x"}]},
)
text, rc = run("demo", "--root", root, "--out", os.path.join(root, "dist"))
check("3 drift exits 2", rc == 2, f"rc={rc} {text}")
check("3 drift names the text", "gone sentence" in text, text)
shutil.rmtree(root, ignore_errors=True)

# 4. A replacement is what makes a kit-bound skill portable.
root = fake_root(
    "---\nname: demo\ndescription: A demo.\n---\n\nRun `kit gate tests`.\n",
    {"replace": [{"from": "`kit gate tests`", "to": "the test suite"}]},
)
text, rc = run("demo", "--root", root, "--out", os.path.join(root, "dist"))
check("4 replaced skill exits 0", rc == 0, text)
shutil.rmtree(root, ignore_errors=True)

# 5. The open standard's limits: name matches the folder, description fits.
root = fake_root("---\nname: other\ndescription: A demo.\n---\n\nBody.\n")
text, rc = run("demo", "--root", root, "--out", os.path.join(root, "dist"))
check("5 name mismatch exits 1", rc == 1, f"rc={rc} {text}")
shutil.rmtree(root, ignore_errors=True)
root = fake_root(f"---\nname: demo\ndescription: {'x' * 1025}\n---\n\nBody.\n")
text, rc = run("demo", "--root", root, "--out", os.path.join(root, "dist"))
check("5 long description exits 1", rc == 1, f"rc={rc} {text}")
shutil.rmtree(root, ignore_errors=True)

# 6. An unknown skill is an error, not an empty package.
text, rc = run("no-such-skill", "--out", tempfile.mkdtemp())
check("6 unknown skill exits 1", rc == 1, f"rc={rc} {text}")

# 7. Every manifest carries the copy its marketplace listing needs.
for name in PORTABLE:
    with open(os.path.join(ROOT, "export", f"{name}.json")) as handle:
        listing = json.load(handle).get("listing", {})
    check(f"7 {name} listing title", bool(listing.get("title")), listing)
    check(f"7 {name} listing summary fits", 0 < len(listing.get("summary", "")) <= 200, listing)
    check(f"7 {name} listing tags", len(listing.get("tags", [])) >= 3, listing)

if failures:
    print(f"FAIL {len(failures)} of {passes + len(failures)}")
    for failure in failures:
        print(f"  {failure}")
    sys.exit(1)
print(f"OK {passes} checks")
