#!/usr/bin/env python3
"""Where a path sits relative to this plugin's own source tree.

Exists for one exemption. A guard that matches on a literal cannot tell a file
that uses the literal from a file that talks about it, and the second kind is
exactly what a test is. Measured while writing tests/test-guards.py: four
consecutive refusals, once for the push flag, once for the short form of it,
once for a skip marker and once for the em dash, each of them a string the test
had to contain in order to assert anything about it. tests/test-hooks.py, which
covers those same rules, is unwritable today for the same reason.

The exemption is deliberately narrow: only `tests/` inside a checkout of this
plugin, identified by its own manifest rather than by the directory name. A
`tests/` directory in a user's repository keeps every guard, because a skipped
test there is the thing the guard exists to catch. That was the choice made
when this was added, over the wider "exempt tests/ anywhere".
"""
import json
import os

MANIFEST = os.path.join(".claude-plugin", "plugin.json")
PLUGIN_NAME = "claude-kit"


def _root_of(path: str):
    """The checkout that owns `path`, if it is one of this plugin's."""
    current = os.path.dirname(os.path.abspath(path))
    while True:
        manifest = os.path.join(current, MANIFEST)
        if os.path.isfile(manifest):
            try:
                with open(manifest, encoding="utf-8") as handle:
                    if json.load(handle).get("name") == PLUGIN_NAME:
                        return current
            except (OSError, ValueError):
                return None
            return None
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def is_own_test(path: str) -> bool:
    """True for a file under `tests/` in a checkout of this plugin."""
    if not path:
        return False
    root = _root_of(path)
    if root is None:
        return False
    tests = os.path.join(root, "tests") + os.sep
    return os.path.abspath(path).startswith(tests)
