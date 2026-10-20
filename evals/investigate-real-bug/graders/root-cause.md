---
type: llm
weight: 3
---

The real cause: `parseBRL` in `src/money.ts` only swaps the first comma for a dot, so
a value with a thousands separator such as "12.500,00" becomes "12.500.00", `Number`
returns NaN, and `toMedicao` in `src/medicao.ts` turns NaN into 0 with `|| 0`. Values
under R$ 1.000 ("850,00") parse fine, which is why it happens only sometimes.

PASS only if the answer identifies that values with a thousands separator (from
R$ 1.000 up) fail to parse and fall back to zero, naming `parseBRL` or `src/money.ts`
and the `|| 0` fallback. FAIL if it only lists possible causes without settling on
this one, or names a different cause.
