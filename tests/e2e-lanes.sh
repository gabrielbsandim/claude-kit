#!/usr/bin/env bash
# The three lanes end to end, on the eval fixture with a git directory the
# agent can write. `claude plugin eval` mounts it read-only, so no eval can grade a
# branch, a commit or the review that reads one. Real sessions on your account, about
# US$ 1 to 4 per lane, so this is not in CI.
# Usage: tests/e2e-lanes.sh [trivial|direct|risk|all]   (E2E_BUDGET caps each lane, default 4)
set -u
PLUGIN="$(cd "$(dirname "$0")/.." && pwd)"
LANES="${1:-all}"
[ "$LANES" = all ] && LANES="trivial direct risk"
fail=0

check() {
  if eval "$2"; then printf 'ok    %s\n' "$1"; return; fi
  printf 'FAIL  %s\n' "$1"
  fail=1
}

# One line per event, in order: AGENT <type>, WRITE <path>, BASH <command>, OUT <tool output line>.
events() {
  python3 - "$1" <<'PY'
import json, sys
for raw in open(sys.argv[1], encoding="utf8"):
    try:
        event = json.loads(raw)
    except ValueError:
        continue
    for block in (event.get("message") or {}).get("content") or []:
        if not isinstance(block, dict):
            continue
        kind, data = block.get("type"), block.get("input") or {}
        if kind == "tool_use" and block.get("name") == "Agent":
            print("AGENT", (data.get("subagent_type") or "").split(":")[-1])
        if kind == "tool_use" and block.get("name") in ("Edit", "Write"):
            print("WRITE", data.get("file_path", ""))
        if kind == "tool_use" and block.get("name") == "Bash":
            print("BASH", " ".join(data.get("command", "").split()))
        if kind == "tool_result":
            content = block.get("content")
            text = content if isinstance(content, str) else " ".join(
                c.get("text", "") for c in content or [] if isinstance(c, dict))
            for line in text.splitlines():
                print("OUT", line)
PY
}

run_lane() {
  local lane="$1" prompt="$2" root
  root="$(mktemp -d)"
  mkdir "$root/cwd"
  (cd "$root/cwd" && bash "$PLUGIN/evals/_fixture/build.sh" >/dev/null)
  printf '\n== %s lane, in %s\n' "$lane" "$root"
  (cd "$root/cwd" && claude -p "$prompt" --plugin-dir "$PLUGIN" --setting-sources project,local \
    --permission-mode bypassPermissions --output-format stream-json --verbose \
    --max-budget-usd "${E2E_BUDGET:-4}") > "$root/trace.jsonl" 2>&1
  events "$root/trace.jsonl" > "$root/events.txt"
  ROOT="$root" EV="$root/events.txt"
  BRANCH="$(git -C "$root/remote.git" for-each-ref refs/heads --format='%(refname:short)' | grep -vx trunk | head -1)"
  printf 'trace %s/trace.jsonl, pushed branch: %s\n' "$root" "${BRANCH:-none}"
}

agents() { grep -c "^AGENT $1\$" "$EV"; }
pushed_touches() { [ -n "$BRANCH" ] && git -C "$ROOT/remote.git" log --name-only --format= "trunk..$BRANCH" | grep -qx "$1"; }

for lane in $LANES; do
  case "$lane" in
    trivial)
      run_lane trivial 'A mensagem de texto longo esta como "Texto maior que o permitido", e o produto quer "Texto acima do limite permitido". Troca e abre a PR. Commit e push estao autorizados, nao precisa me perguntar.'
      check "a branch off trunk was pushed with src/messages.ts" 'pushed_touches src/messages.ts'
      check "trunk on the remote is untouched" '[ "$(git -C "$ROOT/remote.git" rev-list --count trunk)" = 1 ]'
      check "no funnel agent at all (triage, test writer, reviewer, verifier)" '! grep -qE "^AGENT funnel-(triage|test-writer|reviewer|verifier)$" "$EV"'
      check "no issue was created" '! grep -qE "^BASH .*(issue create|/issues)" "$EV"'
      check "the gates ran" 'grep -qE "^BASH .*(ci/(lint|types|test)\.sh|kit\"? gate)" "$EV"'
      ;;
    direct)
      run_lane direct 'A observacao da medicao precisa ser cortada em 500 caracteres, com "..." no fim quando cortar. Cria uma funcao para isso em src/texto.ts e abre a PR. Commit e push estao autorizados, nao precisa me perguntar.'
      check "a branch off trunk was pushed with src/texto.ts" 'pushed_touches src/texto.ts'
      check "trunk on the remote is untouched" '[ "$(git -C "$ROOT/remote.git" rev-list --count trunk)" = 1 ]'
      check "no premise check (funnel-triage) on the direct lane" '[ "$(agents funnel-triage)" = 0 ]'
      check "no funnel-test-writer on the direct lane" '[ "$(agents funnel-test-writer)" = 0 ]'
      check "one review ran (funnel-reviewer dispatched)" '[ "$(agents funnel-reviewer)" -ge 1 ]'
      check "kit review never opened a second round" '! grep -qE "^OUT .*round 2 of" "$EV"'
      ;;
    risk)
      run_lane risk 'O parseBRL quebra com separador de milhar: "12.500,00" nao vira 12500. Corrige. A spec ja esta aprovada: "12.500,00" vira 12500, "850,00" vira 850, "1.234.567,89" vira 1234567.89, texto fora desse formato vira NaN, e src/medicao.ts nao muda. Pode seguir ate a PR sem me perguntar; commit e push estao autorizados.'
      check "a branch off trunk was pushed with src/money.ts" 'pushed_touches src/money.ts'
      check "trunk on the remote is untouched" '[ "$(git -C "$ROOT/remote.git" rev-list --count trunk)" = 1 ]'
      check "the premise check ran (funnel-triage)" '[ "$(agents funnel-triage)" -ge 1 ]'
      check "tests were written by funnel-test-writer" '[ "$(agents funnel-test-writer)" -ge 1 ]'
      check "the tests came before any edit to src/money.ts" 'grep -nE "^(AGENT funnel-test-writer|WRITE .*src/money\.ts)" "$EV" | head -1 | grep -q funnel-test-writer'
      check "a review ran (funnel-reviewer dispatched)" '[ "$(agents funnel-reviewer)" -ge 1 ]'
      check "kit review never opened a third round" '! grep -qE "^OUT .*round 3 of" "$EV"'
      ;;
    *) echo "unknown lane: $lane"; exit 2 ;;
  esac
done

[ "$fail" -eq 0 ] && echo "OK" || echo "FAILED"
exit "$fail"
