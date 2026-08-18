#!/usr/bin/env python3
"""Proves `issues related` answers with evidence and not with enthusiasm.

    python3 tests/test-issues.py

Every case runs against a fixture, so no network and no tracker. The cases are the
two ways this command can be worse than useless:

- **A false yes**, which sends a funnel run to comment on an unrelated issue. The
  cause is always a term shared by everything: in the repository this was written
  against, `docs/security.md` is named by 8 of 17 open issues and "obra" by most
  titles, and an unweighted scorer put an NFS-e issue level with the three that
  really were about work scoping.
- **A false no**, which is the expensive one, because it reads as "nothing similar
  exists" and a duplicate issue gets opened. That is why a provider this command
  cannot search exits non-zero instead of printing an empty list.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISSUES = os.path.join(KIT, "bin", "issues")
PASS, FAIL = 0, 0


def check(name, got, want, compare=lambda a, b: a == b):
    global PASS, FAIL
    if compare(got, want):
        PASS += 1
        print("ok    %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s\n        got  %r\n        want %r" % (name, got, want))


def contains(got, want):
    return want in got


def issue(n, title, files=(), code=(), labels=()):
    body = "Some prose about the change.\n\n"
    body += "".join("- `%s` at %s\n" % (os.path.basename(f), f) for f in files)
    body += "".join("- the `%s` helper\n" % c for c in code)
    return {"number": n, "title": title, "body": body,
            "labels": [{"name": l} for l in labels]}


def run(fixture, *args):
    path = os.path.join(fixture["dir"], "issues.json")
    out = subprocess.run([ISSUES, "related"] + list(args) + ["--json", path],
                         capture_output=True, text=True, cwd=fixture["dir"])
    return out.stdout + out.stderr, out.returncode


def write(root, issues):
    d = tempfile.mkdtemp(dir=root)
    with open(os.path.join(d, "issues.json"), "w") as fh:
        json.dump(issues, fh)
    return {"dir": d}


def main():
    root = tempfile.mkdtemp(prefix="kit-issues-")
    try:
        # A backlog shaped like the real one: one document every issue names, one
        # spine file several name, and per-issue files only one or two name.
        spine = "src/lib/permissions.ts"
        doc = "docs/security.md"
        base = [
            issue(101, "fix(security): the permission catalogue is not the source of truth",
                  files=[doc, spine, "src/lib/getUserPermissions.ts",
                         "src/application/usecases/permissionCatalog.data.ts"],
                  labels=["security", "platform"]),
            issue(102, "fix(security): role belongs to the user and not to the membership",
                  files=[doc, spine, "src/lib/getUserPermissions.ts"],
                  labels=["security", "platform"]),
            issue(103, "fix(security): work scope on the screens and in the assistant",
                  files=[doc, spine, "src/features/team/teamScreen/TeamScreen.tsx"],
                  labels=["security", "works"]),
            issue(104, "feat(financial): issue NFS-e with the national standard",
                  files=[doc, "src/features/financial/nfse/nfseScreen.tsx"],
                  labels=["financial"]),
            issue(105, "feat: client portal MVP",
                  files=["src/features/portal/portalScreen.tsx"], labels=["post-v1"]),
            issue(106, "chore: bump the toolchain", files=["package.json"]),
            issue(107, "fix(diary): the daily report attaches the wrong photo",
                  files=["src/application/usecases/getDailyReportData.ts"], labels=["diary"]),
            issue(108, "fix(whatsapp): the bot answers a deactivated user",
                  files=["src/infra/whatsapp/handleIncoming.ts"], labels=["whatsapp"]),
        ]
        fx = write(root, base)

        # 1. Real overlap: two rare source files in common with #102.
        out, rc = run(fx, "role comes from the user, not the membership",
                      "--files", "%s,src/lib/getUserPermissions.ts" % spine,
                      "--labels", "security", "--exclude", "102")
        check("a query overlapping in rare source files ranks that issue first",
              out.splitlines()[2].split()[0] if len(out.splitlines()) > 2 else out, "#101",
              lambda a, b: a.startswith(b))
        check("and the evidence names the shared file",
              out, "src/lib/getUserPermissions.ts", contains)
        check("the verdict points at the issue, not at nothing",
              out, "#101", contains)

        # 2. Only the document in common. Every issue names it, so this is not a
        #    duplicate signal, and calling it one is the false yes that matters.
        out, rc = run(fx, "the daily report needs a different photo rule",
                      "--files", doc, "--labels", "security")
        check("sharing only the document does not read as the same work",
              out, "wording only", contains)
        check("and the document is still shown as what matched", out, doc, contains)

        # 2b. What the damping is for: at equal rarity, a shared source file has to
        #     outrank a shared document. Both are named by exactly two issues here,
        #     so only the damping separates them.
        rank_fx = write(root, [
            issue(401, "the ledger posts the wrong category", files=["docs/one.md"]),
            issue(402, "the roster hides an allocation", files=["src/lib/roster.ts"]),
            issue(403, "unrelated", files=["src/lib/z.ts"]),
            issue(404, "also unrelated", files=["src/lib/y.ts"]),
        ])
        out, rc = run(rank_fx, "a change touching both",
                      "--files", "docs/one.md,src/lib/roster.ts")
        first = next((l for l in out.splitlines() if l.startswith("#")), "")
        check("a shared source file outranks a shared document of equal rarity",
              first.split()[0] if first else out, "#402", lambda a, b: a == b)

        # 3. Nothing in common at all.
        out, rc = run(fx, "the invoice pdf renders upside down",
                      "--files", "src/lib/pdf/rotate.ts")
        check("no overlap says so plainly", out, "nothing to merge into", contains)
        check("and exits zero, because no overlap is a normal answer", rc, 0)

        # 4. The shared prefix in every title must not be a match on its own.
        out, rc = run(fx, "fix(security): something entirely unrelated",
                      "--files", "src/lib/pdf/rotate.ts")
        check("the conventional prefix is not evidence", out, "nothing to merge into", contains)

        # 5. An identifier in backticks matches across different prose.
        code_fx = write(root, [
            issue(201, "fix: the resolver returns the wrong set", code=["listAccessibleWorkIds"],
                  files=["src/lib/a.ts"]),
            issue(202, "chore: unrelated", files=["src/lib/z.ts"]),
        ])
        out, rc = run(code_fx, "the `listAccessibleWorkIds` helper answers [] for a role that should see all",
                      "--exclude", "0")
        check("an identifier in backticks finds the issue about it", out, "#201", contains)
        check("and names it as the code match", out, "listaccessibleworkids", contains)

        # 6. A file every single issue names carries zero weight, so it cannot rank
        #    or decide anything. Two issues, both naming it, nothing else shared.
        flat_fx = write(root, [
            issue(301, "one thing", files=["README.md"]),
            issue(302, "another thing", files=["README.md"]),
        ])
        out, rc = run(flat_fx, "a third thing", "--files", "README.md")
        check("a term present in every issue cannot produce a match",
              out, "nothing to merge into", contains)

        # 7. --exclude keeps the issue itself out of its own corpus.
        out, rc = run(fx, "the permission catalogue is not the source of truth",
                      "--files", "%s,src/application/usecases/permissionCatalog.data.ts" % spine,
                      "--exclude", "101")
        check("--exclude removes the issue from its own results", "#101 " in out, False)

        # 8. Ranking is stable: same input, same order, twice.
        a1, _ = run(fx, "role and membership", "--files", spine)
        a2, _ = run(fx, "role and membership", "--files", spine)
        check("the ranking is deterministic", a1, a2)

        # 9. A tracker this command cannot search must not answer "nothing similar".
        jira = tempfile.mkdtemp(dir=root)
        subprocess.run(["git", "init", "-q", jira], check=True)
        os.makedirs(os.path.join(jira, ".claude"))
        with open(os.path.join(jira, ".claude/board.json"), "w") as fh:
            json.dump({"provider": "jira"}, fh)
        with open(os.path.join(jira, ".claude/funnel.config.json"), "w") as fh:
            fh.write('{"base":"main","gates":{},"stages":{},"slices":{},"lenses":{},"effort":{}}')
        out = subprocess.run([ISSUES, "related", "anything"], capture_output=True,
                             text=True, cwd=jira)
        check("a non-GitHub board refuses instead of returning nothing", out.returncode, 2)
        check("and says to search that board by hand",
              out.stdout + out.stderr, "by hand", contains)

        # 10. orphans needs the tracker: the parent link is not in the list payload,
        #     so a fixture answer would be a lie.
        out = subprocess.run([ISSUES, "orphans", "--json",
                              os.path.join(fx["dir"], "issues.json")],
                             capture_output=True, text=True, cwd=fx["dir"])
        check("orphans refuses to answer from a fixture", out.returncode, 2)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
