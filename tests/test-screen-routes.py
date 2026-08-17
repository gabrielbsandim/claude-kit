#!/usr/bin/env python3
"""Proves bin/screen-routes on a fixture repo, because a wrong route sends the
browser lens to prove a screen the branch never touched.

    python3 tests/test-screen-routes.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(KIT, "bin", "screen-routes")
PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("ok    %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s\n        got  %r\n        want %r" % (name, got, want))


def write(root, path, body=""):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(body)


def git(root, *args):
    subprocess.run(["git"] + list(args), cwd=root, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_repo(root, browser):
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    write(root, "tsconfig.json", json.dumps(
        {"compilerOptions": {"paths": {"@/*": ["src/*"]}}}))
    write(root, ".claude/funnel.config.json", json.dumps({
        "base": "main",
        "gates": {}, "stages": {}, "slices": {"all": "{base}...HEAD"},
        "lenses": {}, "effort": {}, "browser": browser,
    }))
    # Router entry points. The group and the slot must not reach the URL.
    write(root, "src/app/(dashboard)/procurement/page.tsx",
          "import { Screen } from '@/features/procurement/Screen'\nexport default Screen")
    write(root, "src/app/(dashboard)/suppliers/[id]/page.tsx",
          "import { Detail } from '@/features/suppliers/Detail'\nexport default Detail")
    write(root, "src/app/(marketing)/@modal/pricing/page.tsx", "export default () => null")
    write(root, "src/app/docs/[...slug]/page.tsx",
          "import { Docs } from '../../../features/docs/Docs'\nexport default Docs")
    write(root, "src/app/api/things/route.ts", "export const GET = () => null")
    # Components, one of them two hops from its entry point.
    write(root, "src/features/procurement/Screen.tsx",
          "import { Table } from '@/components/Table'\nexport const Screen = () => Table")
    write(root, "src/components/Table.tsx", "export const Table = null")
    write(root, "src/features/suppliers/Detail.tsx", "export const Detail = null")
    write(root, "src/features/docs/Docs.tsx", "export const Docs = null")
    write(root, "src/features/orphan/Lonely.tsx", "export const Lonely = null")
    write(root, "src/components/Table.test.tsx", "test('x', () => {})")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


def run(root, *extra):
    out = subprocess.run([sys.executable, SCRIPT, "--json"] + list(extra),
                         cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return {"error": out.stderr.strip()}
    return json.loads(out.stdout)


def touch_and_run(root, paths, browser=None):
    # Back to base first: without this every case inherits the previous case's
    # diff, and the suite passes or fails for a reason no assertion states.
    git(root, "reset", "--hard", "-q", "refs/remotes/origin/main")
    if browser is not None:
        cfg = json.load(open(os.path.join(root, ".claude/funnel.config.json")))
        cfg["browser"] = browser
        write(root, ".claude/funnel.config.json", json.dumps(cfg))
    for p in paths:
        with open(os.path.join(root, p), "a", encoding="utf-8") as fh:
            fh.write("\n// touched\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "change")
    return run(root)


def main():
    base_browser = {"enabled": True, "baseUrl": "http://localhost:3000",
                    "appDir": "src/app", "maxRoutes": 6}

    root = tempfile.mkdtemp(prefix="kit-screens-")
    try:
        build_repo(root, base_browser)

        # A component two hops below its page still resolves, and the route group
        # is not part of the URL.
        r = touch_and_run(root, ["src/components/Table.tsx"])
        check("component two hops up resolves to its page",
              [(v["route"], v["via"]) for v in r["visit"]],
              [("/procurement", "src/app/(dashboard)/procurement/page.tsx")])

        # A dynamic segment with no configured value is blocked, not silently
        # visited as the literal "[id]".
        r = touch_and_run(root, ["src/features/suppliers/Detail.tsx"])
        check("dynamic segment with no param is blocked", r["visit"], [])
        check("dynamic segment names the missing param",
              [b["missingParams"] for b in r["blocked"]], [["id"]])

        # With the value configured it becomes a real URL.
        b = dict(base_browser, routeParams={"id": "sup-1"})
        r = touch_and_run(root, ["src/features/suppliers/Detail.tsx"], b)
        check("configured param produces a real url",
              [v["route"] for v in r["visit"]], ["/suppliers/sup-1"])

        # A relative import resolves, and a catch-all reads its parameter name
        # the same way a plain dynamic segment does.
        b = dict(base_browser, routeParams={"slug": "getting-started"})
        r = touch_and_run(root, ["src/features/docs/Docs.tsx"], b)
        check("relative import and catch-all resolve",
              [v["route"] for v in r["visit"]], ["/docs/getting-started"])

        # Nothing imports this one, so there is no route to prove and it has to
        # say so rather than report a clean run.
        r = touch_and_run(root, ["src/features/orphan/Lonely.tsx"])
        check("file no entry point imports is reported blocked",
              [(b["route"], b["via"]) for b in r["blocked"]],
              [(None, "no router entry point imports this file")])

        # An api route and a test file are not screens.
        r = touch_and_run(root, ["src/app/api/things/route.ts",
                                 "src/components/Table.test.tsx"])
        check("api route and test file are not screens", r["changedScreens"], 0)

        # A named slot segment is dropped from the URL like a group is.
        r = touch_and_run(root, ["src/app/(marketing)/@modal/pricing/page.tsx"])
        check("named slot is dropped from the url",
              [v["route"] for v in r["visit"]], ["/pricing"])

        # The cap is announced, never silent.
        b = dict(base_browser, maxRoutes=1, routeParams={"id": "sup-1", "slug": "s"})
        r = touch_and_run(root, ["src/features/procurement/Screen.tsx",
                                 "src/features/suppliers/Detail.tsx"], b)
        check("cap keeps one route", len(r["visit"]), 1)
        check("cap reports what it dropped", len(r["droppedByCap"]), 1)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
