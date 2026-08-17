#!/usr/bin/env python3
"""Validates the eval suite's frontmatter offline.

`claude plugin eval` errors on an unknown key, and the harness is early access, so
this catches the whole class of mistake without an API call or an enablement flag.
The allowed sets come from the harness's own reference: prompt.md carries case fields,
case.yaml carries the ones prompt.md cannot (context.*), each grader declares a type
and only that type's keys.

Run: python3 tests/check-eval-schema.py
"""
import glob
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("pyyaml nao instalado, checagem de schema pulada")
    sys.exit(0)

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals")
PROMPT_KEYS = {
    "schema_version", "name", "description", "tags", "plugins", "runs", "expected_outcome",
    "model", "max_turns", "timeout_seconds", "allowed_tools", "append_system_prompt", "env",
}
CONTEXT_KEYS = {"scaffold_script", "history_file", "add_dirs"}
GRADER_COMMON = {"type", "name", "weight", "arm"}
GRADER_KEYS = {
    "regex": {"pattern", "flags", "match", "target"},
    "tool_used": {"tool", "input_match", "min", "max"},
    "tool_order": {"before", "after"},
    "file_exists": {"path", "exists"},
    "llm": {"criteria", "focus"},
    "baseline": {"baseline_file", "criteria"},
}

problems = []


def frontmatter(path):
    text = open(path, encoding="utf8").read()
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not match:
        return None, text
    return yaml.safe_load(match.group(1)) or {}, match.group(2)


def fail(msg):
    problems.append(msg)
    print(f"FALHA  {msg}")


cases = [d for d in sorted(os.listdir(ROOT)) if os.path.isdir(os.path.join(ROOT, d))]
if not cases:
    fail("nenhum caso em evals/")

for case in cases:
    if case == "results":
        continue
    base = os.path.join(ROOT, case)
    prompt = os.path.join(base, "prompt.md")
    yml = os.path.join(base, "case.yaml")
    if not os.path.exists(prompt) and not os.path.exists(yml):
        fail(f"{case}: sem prompt.md nem case.yaml")
        continue

    if os.path.exists(prompt):
        data, body = frontmatter(prompt)
        if data is None:
            fail(f"{case}/prompt.md: sem frontmatter")
        else:
            for key in set(data) - PROMPT_KEYS:
                fail(f"{case}/prompt.md: chave desconhecida {key!r}")
            if not body.strip():
                fail(f"{case}/prompt.md: corpo vazio, nao ha prompt para enviar")

    if os.path.exists(yml):
        data = yaml.safe_load(open(yml, encoding="utf8")) or {}
        for req in ("schema_version", "name"):
            if req not in data:
                fail(f"{case}/case.yaml: falta {req}, obrigatorio quando case.yaml existe")
        for key in set(data.get("context") or {}) - CONTEXT_KEYS:
            fail(f"{case}/case.yaml: context.{key} desconhecido")

    graders = sorted(glob.glob(os.path.join(base, "graders", "*.md")))
    if not graders and "graders" not in (yaml.safe_load(open(yml, encoding="utf8")) or {} if os.path.exists(yml) else {}):
        fail(f"{case}: nenhum grader, o caso nao pontua nada")
    for path in graders:
        name = os.path.relpath(path, ROOT)
        data, body = frontmatter(path)
        if data is None:
            continue  # files with no frontmatter are ignored by the harness
        kind = data.get("type")
        if kind not in GRADER_KEYS:
            fail(f"{name}: type {kind!r} nao existe")
            continue
        for key in set(data) - GRADER_COMMON - GRADER_KEYS[kind]:
            fail(f"{name}: chave {key!r} nao vale para type {kind}")
        if data.get("weight", 1) is not None and float(data.get("weight", 1)) <= 0:
            fail(f"{name}: weight tem de ser maior que zero")
        if kind in ("llm", "baseline") and not body.strip() and "criteria" not in data:
            fail(f"{name}: grader {kind} sem criteria")
        if kind == "tool_used":
            lo, hi = data.get("min", 1), data.get("max")
            if hi is not None and hi < lo:
                fail(f"{name}: max {hi} menor que min {lo}, nunca passa")

print()
if problems:
    print(f"{len(problems)} problema(s)")
    sys.exit(1)
print(f"{len(cases)} caso(s), schema ok")
