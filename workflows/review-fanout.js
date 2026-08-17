export const meta = {
  name: 'review-fanout',
  description:
    'Runs the funnel review stage as a deterministic fan-out: read the grouped dispatch plan, review each slice as one multi-part contract, then adversarially verify each finding before it can send anyone back to the implementer.',
  whenToUse:
    'The review stage of a task that is already implemented and committed in a worktree. Not the whole funnel: the rest has gates a human answers, and a workflow cannot ask.',
  phases: [
    { title: 'Plan', detail: 'read kit review --dispatches and return the groups' },
    { title: 'Review', detail: 'one dispatch per slice, every lens as a numbered part' },
    { title: 'Verify', detail: 'try to refute each finding before it costs a round' },
  ],
}

// Why only this stage is a workflow, when the rest of the funnel is a skill:
//
// A workflow is deterministic control flow with no way to stop and ask. Four of the
// funnel's gates are decisions a human owns: triage returning NEEDS_DECISION, "this is
// too big for one pull request", showing the spec before the environment is paid for,
// and the written adjudication at the round cap. Encoding those as script means either
// dropping the question or answering it on the user's behalf, and answering on their
// behalf is exactly what turned a 45-minute task into five hours the first time.
//
// The review stage is the opposite: the work is already committed, the plan is computed
// by `kit review --dispatches`, the dispatches are read-only and disjoint by
// construction, and nothing in it needs a human until the findings come back. That is
// what a workflow is for.

const PLAN = {
  type: 'object',
  required: ['dispatches'],
  properties: {
    dispatches: {
      type: 'array',
      items: {
        type: 'object',
        required: ['parts', 'diffFile', 'changedLines'],
        properties: {
          parts: { type: 'array', items: { type: 'string' } },
          diffFile: { type: 'string' },
          docs: { type: 'array', items: { type: 'string' } },
          changedLines: { type: 'number' },
          proseCandidates: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

const FINDINGS = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['lens', 'grade', 'file', 'claim'],
        properties: {
          lens: { type: 'string' },
          grade: { type: 'string', enum: ['Critical', 'Important', 'Minor'] },
          file: { type: 'string' },
          line: { type: 'number' },
          claim: { type: 'string' },
          evidence: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT = {
  type: 'object',
  required: ['refuted', 'why'],
  properties: {
    refuted: { type: 'boolean' },
    why: { type: 'string' },
  },
}

const level = (args && args.level) || 'standard'
const since = args && args.since
const spec = (args && args.spec) || '(no spec text was passed; grade against the diff alone and say so)'

phase('Plan')
const plan = await agent(
  `Run this and return its content as structured data. Do not review anything.

    kit review ${level}${since ? ` --since ${since}` : ''}

It prints one block per dispatch: the parts (lens names), the absolute path of a diff
file that is already written, the documents to read, the changed-line count, and for the
claims part a grep-precomputed candidate list. Return exactly those fields. If the
command fails, return an empty dispatches array and put the error in the first part
name.`,
  { label: 'plan', phase: 'Plan', schema: PLAN },
)

if (!plan || !plan.dispatches?.length) {
  log('no dispatches; is there a committed diff against the base branch in this worktree?')
  return { confirmed: [], deferred: [], note: 'kit review returned no dispatches' }
}

log(
  `${plan.dispatches.length} dispatch(es), ${plan.dispatches.reduce((n, d) => n + (d.changedLines || 0), 0)} changed lines total`,
)

// pipeline, not parallel: a dispatch that finishes early starts verifying while the
// slowest one is still reading. A barrier here would idle every fast reviewer until the
// biggest slice came back, and the slices differ in size by design.
const reviewed = await pipeline(
  plan.dispatches,
  (dispatch) =>
    agent(
      `You are one review dispatch inside the task funnel. Answer every part below, in
order, from a single read of the diff.

PARTS: ${dispatch.parts.join(', ')}

DIFF: ${dispatch.diffFile}
The file is already written. Read it once. Its context lines are the changed file.
Do not run git. Do not open the file again unless a hunk is visibly cut off.
Do not sweep the codebase; look outside the diff only for a risk you can name, as one
focused check, naming both the risk and the check.
Do not run the test suite; the implementer already did.
Do not dispatch subagents.

READ: ${dispatch.docs?.length ? dispatch.docs.join(', ') : 'nothing beyond the diff'}
${
  dispatch.proseCandidates?.length
    ? `PROSE CANDIDATES (grep-precomputed, verify each against the code as committed):\n${dispatch.proseCandidates.join('\n')}`
    : ''
}

SPEC: ${spec}

GRADE each finding:
  Critical  data loss, security, money, production breaks
  Important the task is not trustworthy until fixed: incorrect or fragile behaviour, a
            missed requirement, a literal duplicated block of logic, a swallowed error,
            a test that asserts nothing
  Minor     naming, style, "coverage could be broader", a preference

Every finding carries the input and the wrong output, or the line that cannot do what
the spec requires. If you cannot state that, it is not a finding yet: say what would
prove it and grade it Minor.`,
      { label: `review:${dispatch.parts[0]}`, phase: 'Review', schema: FINDINGS },
    ),

  // Minor never enters the loop, so it never buys a verifier either.
  (result, dispatch) => {
    const worth = (result?.findings ?? []).filter((f) => f.grade !== 'Minor')
    const deferred = (result?.findings ?? []).filter((f) => f.grade === 'Minor')
    if (!worth.length) {
      log(`${dispatch.parts.join('+')}: nothing above Minor`)
      return { verified: [], deferred }
    }
    return parallel(
      worth.map((finding) => () =>
        agent(
          `Try to REFUTE this review finding. You are not here to agree with it.

CLAIM: ${finding.claim}
WHERE: ${finding.file}${finding.line ? `:${finding.line}` : ''}
GRADE: ${finding.grade}
EVIDENCE OFFERED: ${finding.evidence ?? '(none)'}
DIFF: ${dispatch.diffFile}

A finding survives only if you can trace the input to the wrong output in the code as
committed. Default to refuted:true when you are uncertain, when the evidence is a
restatement of the claim, or when the reasoning depends on code the diff does not
contain. A finding that does not reproduce costs a full review round, which is 30 to 70
minutes, so a false confirm is more expensive than a false refute.`,
          { label: `verify:${finding.file}`, phase: 'Verify', schema: VERDICT },
        ).then((v) => ({ ...finding, verdict: v })),
      ),
    ).then((verified) => ({ verified: verified.filter(Boolean), deferred }))
  },
)

const rows = reviewed.filter(Boolean)
const confirmed = rows.flatMap((r) => r.verified).filter((f) => f.verdict && !f.verdict.refuted)
const refuted = rows.flatMap((r) => r.verified).filter((f) => f.verdict && f.verdict.refuted)
const deferred = rows.flatMap((r) => r.deferred ?? [])

log(
  `${confirmed.length} confirmed, ${refuted.length} refuted by the verifier, ${deferred.length} deferred as Minor`,
)

// The deferred list is data on purpose. Minor findings written into a pull request body
// as prose are how a two-round cap becomes four rounds.
return {
  confirmed: confirmed.map((f) => ({
    lens: f.lens,
    grade: f.grade,
    at: `${f.file}${f.line ? `:${f.line}` : ''}`,
    claim: f.claim,
    why: f.verdict.why,
  })),
  refuted: refuted.map((f) => ({ at: f.file, claim: f.claim, why: f.verdict.why })),
  deferred: deferred.map((f) => ({ at: f.file, claim: f.claim })),
}
