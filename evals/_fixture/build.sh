#!/usr/bin/env bash
# The eval sandbox blocks writes to .git, so the cases grade the commands the agent tried.
# Usage: build.sh [ship-red], where ship-red also leaves a finished branch whose lint fails.
set -e
ROOT="$(pwd)"
mkdir -p .claude ci docs src "$ROOT/../remote.git"

git init -q --bare "$ROOT/../remote.git"

git init -q -b trunk .
git config user.email eval@example.com
git config user.name eval

for gate in lint types test; do printf '#!/bin/sh\n' > "ci/$gate.sh"; done
cat >> ci/lint.sh <<'GATE'
if grep -rn "console.log" src; then echo "lint: console.log is not allowed in src"; exit 1; fi
GATE
cat >> ci/types.sh <<'GATE'
grep -q "export function parseBRL" src/money.ts || { echo "types: parseBRL is missing"; exit 1; }
GATE
cat >> ci/test.sh <<'GATE'
grep -q "Campo obrigat" src/messages.ts || { echo "test: required-field message is missing"; exit 1; }
GATE

cat > .claude/funnel.config.json <<'CFG'
{
  "base": "trunk",
  "docs": { "entry": "docs/flow.md", "pipeline": "docs/flow.md" },
  "worktree": { "path": "../obra-{issue}", "setup": [], "skipSetupWhenDocOnly": true },
  "gates": {
    "lint":  { "cmd": "sh ci/lint.sh" },
    "types": { "cmd": "sh ci/types.sh" },
    "test":  { "cmd": "sh ci/test.sh" }
  },
  "stages": {
    "implement_first_pass": ["lint", "types", "test"],
    "tests": ["test"],
    "ship": ["lint", "types", "test"]
  },
  "slices": {
    "src": "origin/trunk...HEAD -- src",
    "all": "origin/trunk...HEAD"
  },
  "lenses": {
    "correctness": { "slice": "src", "docs": [] }
  },
  "effort": { "light": ["correctness"], "standard": ["correctness"], "deep": ["correctness"] },
  "ledger": false
}
CFG

cat > docs/flow.md <<'DOC'
# Flow
One task, one branch, one pull request. Never commit or push to trunk.
Before a push, every gate in .claude/funnel.config.json must be green.
DOC

cat > src/messages.ts <<'SRC'
export const messages = {
  required: "Campo obrigatorio",
  tooLong: "Texto maior que o permitido",
  approved: "Medição aprovada",
};
SRC

cat > src/money.ts <<'SRC'
// Values come from the form as Brazilian text: "850,00" or "12.500,00".
export function parseBRL(text: string): number {
  return Number(text.trim().replace(",", "."));
}
SRC

cat > src/medicao.ts <<'SRC'
import { parseBRL } from "./money";

export interface MedicaoInput {
  id: string;
  status: "rascunho" | "enviada" | "aprovada";
  valorMedido: string;
  valorPago: string;
}

export interface Medicao {
  id: string;
  status: MedicaoInput["status"];
  valorMedido: number;
  valorPago: number;
}

export function toMedicao(input: MedicaoInput): Medicao {
  const valorMedido = parseBRL(input.valorMedido) || 0;
  const valorPago = input.status === "aprovada" ? parseBRL(input.valorPago) || 0 : 0;
  return { id: input.id, status: input.status, valorMedido, valorPago };
}

export function aprovar(m: Medicao, gestor: string): Medicao {
  if (m.status !== "enviada") throw new Error("Só medição enviada pode ser aprovada");
  return { ...m, status: "aprovada" };
}
SRC

git add -A
git commit -qm "chore: initial billing module"
git remote add origin "$ROOT/../remote.git"
git push -q origin trunk

if [ "$1" = "ship-red" ]; then
  git switch -q -c feat/observacao
  cat >> src/medicao.ts <<'SRC'

export function observacao(m: Medicao, texto: string): string {
  console.log("observacao", m.id, texto);
  return texto.slice(0, 500);
}
SRC
  git commit -qam "feat: add observation to measurement"
fi
