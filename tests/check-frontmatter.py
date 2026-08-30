#!/usr/bin/env python3
"""Parses every frontmatter block in this plugin with a strict YAML parser.

    python3 tests/check-frontmatter.py

Claude Code reads this frontmatter with a lenient parser, so an unquoted
description containing a colon and a space loads fine and nothing says otherwise.
A strict parser refuses it: a plain YAML scalar cannot contain ": ". Measured on
2026-08-23, five of this plugin's own files were in that state, four found by
`npx agnix` and the fifth, commands/backlog.md, only by PyYAML. Every one of them
had a description written as prose with a colon in it.

That matters the moment anything other than Claude Code reads these files: a
linter, a marketplace index, a generator, or the next tool this plugin ships for.
The fix is to quote the value, and this is the check that keeps it quoted.

Skips itself when PyYAML is missing rather than failing, the same as
check-eval-schema.py, because a missing dependency is not a broken plugin.
"""
import glob
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("pyyaml is not installed, frontmatter check skipped")
    sys.exit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Each pattern with the keys that kind of file must declare.
KINDS = [
    ("agents/*.md", {"name", "description"}),
    ("skills/*/SKILL.md", {"name", "description"}),
    ("commands/*.md", {"description"}),
    ("output-styles/*.md", {"name", "description"}),
]
PASS = []
FAIL = []


def check(name, ok, detail=""):
    if ok:
        PASS.append(name)
        print("ok    %s" % name)
    else:
        FAIL.append(name)
        print("FAIL  %s\n        %s" % (name, detail))


for pattern, required in KINDS:
    paths = sorted(glob.glob(os.path.join(ROOT, pattern)))
    if not paths:
        check(pattern, False, "no file matched, the layout moved")
        continue
    for path in paths:
        rel = os.path.relpath(path, ROOT)
        text = open(path, encoding="utf8").read()
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not match:
            check(rel, False, "no frontmatter block")
            continue
        try:
            data = yaml.safe_load(match.group(1))
        except yaml.YAMLError as err:
            first = str(err).splitlines()[0]
            check(rel, False, "not valid YAML: %s. Quote the value." % first)
            continue
        if not isinstance(data, dict):
            check(rel, False, "frontmatter is %s, not a mapping" % type(data).__name__)
            continue
        missing = required - set(data)
        check(rel, not missing, "missing %s" % ", ".join(sorted(missing)))

# The funnel agents declare their model in frontmatter, and the task skill prints
# the same value in a column so that a dispatch never has to guess it. Two places
# holding one value is exactly the drift this file exists for, and this one costs
# money when it drifts: measured over thirteen days, 101 of 625 dispatches carried
# a `model` the orchestrator wrote itself, ten of them overriding the test writer's
# `sonnet` with Opus at 3.6 times the cost per execution.
skill = os.path.join(ROOT, "skills/task/SKILL.md")
if os.path.exists(skill):
    body = open(skill, encoding="utf8").read()
    for path in sorted(glob.glob(os.path.join(ROOT, "agents/funnel-*.md"))):
        name = os.path.basename(path)[: -len(".md")]
        block = re.match(r"^---\n(.*?)\n---\n", open(path, encoding="utf8").read(), re.S)
        declared = (yaml.safe_load(block.group(1)) or {}).get("model") if block else None
        check("agents/%s.md declares a model" % name, bool(declared),
              "no model key: the dispatch has nothing to read it from")
        if not declared:
            continue
        row = re.search(r"^\|.*`claude-kit:%s`\s*\|\s*(\S+)\s*\|" % re.escape(name),
                        body, re.M)
        check("SKILL.md lists %s" % name, bool(row),
              "the agent table has no row for it")
        if row:
            check("SKILL.md agrees that %s is %s" % (name, declared),
                  row.group(1) == declared,
                  "frontmatter says %r, the table says %r" % (declared, row.group(1)))
    # Whitespace-normalised: the rule is a wrapped paragraph, and a line break
    # landing inside the sentence is not the rule going missing.
    check("SKILL.md forbids a hand-written model",
          "never write a `model` field into a dispatch" in " ".join(body.split()),
          "the rule that keeps the frontmatter binding is gone")

print("\n%d ok, %d failed" % (len(PASS), len(FAIL)))
sys.exit(1 if FAIL else 0)
