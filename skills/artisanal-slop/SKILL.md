---
name: artisanal-slop
description: Mostly-automated issue resolution loop — classify (Haiku), triage & plan (Opus sub-agent), implement (Sonnet sub-agent), independently review (Opus/Sonnet tiered by severity), and merge open GitHub issues continuously. A bash state machine owns the decision tree; you execute its directives. Non-blocking — user approval gates only issue-closes and PR merges, and work on the next issue continues while approval is pending.
disable-model-invocation: true
argument-hint: "[issue number to start with]"
license: WTFPL-2.0
metadata:
  tagline: "Works your open GitHub issues end to end — classify, plan, implement, review, merge."
  tags: "github, automation, sub-agents, worktrees"
  requires: "bash 4+, git, gh, coreutils"
---

# Artisanal Slop — hand-crafted, small-batch issue resolution

**You do not decide what happens next — `bin/artisanal-slop` does.** It is a bash state
machine that owns the whole decision tree: issue ranking, the concurrency cap, review
round counting, the park rule, reviewer tiering, prompt rendering, the `gh` sequences,
CI polling, and the post-merge conflict scan. You are its hands: you run it, execute
the one ACTION it prints, and report the outcome back to it.

That split is what makes an indefinite loop affordable and compaction-safe. Sub-agents
do all the deep work; the script holds all the state. Your context stays nearly empty,
so **never investigate code or write fixes yourself.**

Set this once at the start and use it throughout:

```bash
LOOP=~/.claude/skills/artisanal-slop/bin/artisanal-slop
```

## The protocol

```
$LOOP init [--start N]      # once, at the beginning
$LOOP next                  # -> exactly one ACTION block
  <execute that ACTION>
$LOOP record ...            # the THEN: line of the ACTION block
$LOOP next                  # -> the next ACTION
  ...
```

Every ACTION block ends with a `THEN:` line giving the exact command to run once you
have executed it. Follow it literally, substituting the placeholders in angle brackets.
Run `$LOOP next` again after every `record`, and after every background-agent
completion notification.

Run continuously until the script prints `ACTION: done`, or the user stops you. There
is no "shall I continue?" prompt — the user will interject when they want to end it.

## Executing each ACTION

**`ACTION: spawn-agent`** — call `Agent` with exactly the `MODEL`, `SUBAGENT_TYPE`, and
`BACKGROUND` values given, pass the `DESCRIPTION:` line verbatim as the `description`,
and pass the one-line `PROMPT:` verbatim. The sub-agent reads its own brief from
`PROMPT_FILE`, so **do not read that file yourself** — that is what keeps your context
small and the brief intact.

`DESCRIPTION:` is what names the agent in the UI — `Reviewing #12: seek offset
overflow`. It comes from a short summary the classifier wrote in the same pass that
assigned the severity, falling back to a trimmed issue title. Pass it as given rather
than writing your own; it is the only place an agent's identity is visible while it
runs, so consistent wording across stages is what makes a list of live agents
readable. It is a label only — it changes nothing about the reviewer's clean context.

⚠️ **`ISOLATION: none` means do not pass `isolation: "worktree"`.** The script owns
isolation: it hands the agent a pooled worktree in the `WORKTREE:` line, and the
prompt file already tells the agent to work there. Adding harness isolation would give
it a fresh empty worktree instead and throw away the whole point of the pool.

If the block has an `ANNOUNCE:` line, say it in the conversation in one line. If it has
a `STOP_AGENT:` line, stop that agent (`TaskStop`) or discard its verdict first — its
work has been invalidated. Then run the `THEN:` command with the agent's name or id.

When a background agent finishes, read its final message and run the matching `record`:

| Stage | Record the result with |
|---|---|
| `classify` | `$LOOP record classified --from-file <the file it wrote>` |
| `plan` / `replan` | `$LOOP record plan-done N --verdict <its verdict> --category <its CATEGORY> --plan-file\|--comment-file\|--writeup-file <path> --summary "<its SUMMARY>"` |
| `implement` | `$LOOP record impl-done N --pr <num> --url <url> --branch <branch>`, or `impl-failed N --note-file <path>` |
| `fix` | `$LOOP record impl-fixed N` — or, if it replies `PREMISE CHANGED`, `$LOOP replan N --merged-pr <num>` |
| `review` | `$LOOP record review-done N --verdict APPROVE`, or `--verdict REQUEST-CHANGES --findings-file <path>` |
| `conflict-triage` | `$LOOP record triaged-conflicts --from-file <the file it wrote>` |
| `docs` | `$LOOP record docs-done --pr <num> --url <url>`, or `docs-none --reason "<why>"` |

A planner that reports `DOCS_EXEMPT: yes` — the issue's subject *is* an agent-guidance
file — needs `--docs-exempt` added to its `record plan-done`.

The agents write their deliverables to files and name the paths in their final
messages; pass those paths through. Do not paste plans, findings, or diffs into your
own context.

**`ACTION: send-message`** — `SendMessage` the agent named in `TO:` with the `MESSAGE:`
text verbatim, then run `THEN:`. This now happens in exactly one situation: telling a
*live* implementer that `main` moved under it. Everything else that used to be a relay
is a fresh `fix` agent against the issue's persistent worktree instead.

**`ACTION: ask-approval`** — the only synchronous points in the whole loop. Batch every
question in the block into **one** `AskUserQuestion` call (it takes up to 4), using the
`QUESTION:` and `OPTION_A/B:` text as given. For a close question, read the
`DRAFT_COMMENT_FILE` first only if you need a one-line gloss. Then run the `ON_A:` or
`ON_B:` command matching their answer. For an `ON_B` that wants a `--feedback-file`,
write the user's feedback to a file and pass its path.

Background agents keep running while the question is pending — that is the point. The
script already ensured the pipeline was primed before it offered you this action.

**`ACTION: poll-ci`** — run the `RUN:` command. It checks GitHub Actions and records
the result itself, printing `PASS`, `FAIL`, `PENDING`, or `NONE`. On `PENDING`, go do
other work; never block on CI.

**`ACTION: wait`** — everything runnable is running. Stop and wait for the next agent
completion notification. Do not poll in a loop.

**`ACTION: done`** — run `$LOOP summary` and present its table to the user. Note that
`done` comes *after* the documentation phase below, not instead of it.

## What is still your judgment

The script does the mechanics. These remain yours:

- Reading each agent's final message and mapping it to the right `record` event and
  flags. If an agent's report is ambiguous or contradicts itself, treat that as a
  failure rather than guessing a verdict.
- Announcing transitions in the conversation, briefly — one line each.
- Relaying `TELL_USER:` lines the script emits (parked issues, failed implementations,
  needs-human notifications) in your own words.
- Judging when something has gone off the rails badly enough to stop and ask the user
  something the script has no directive for.

## Invariants the script enforces (do not work around them)

- **Never block work on a human.** Approval questions are only offered when the
  pipeline is full or the queue is empty, so waiting on the user never means nothing is
  executing.
- **At most 2 issues in flight** (`ARTISANAL_SLOP_MAX_INFLIGHT`), counting planning and
  awaiting-approval. More multiplies merge conflicts between sibling PRs without
  saving wall-clock time.
- **The repo root stays clean**, on the default branch, at all times. Agents work in
  pooled worktrees under `<state>/pool/slot-N`; the root is used only for read-only
  `git`/`gh` queries and the `git pull --ff-only` after each merge. The script asserts
  this on every `next` and `record` and **halts the loop** if the root is dirty — that
  assertion is the guard that replaces harness-enforced isolation, so if it ever fires,
  an agent ignored its slot and that is worth investigating rather than overriding.
- **The reviewer gets a clean context, every round.** Its prompt file contains the
  issue and PR numbers and nothing else — no plan, no implementation summary, none of
  the implementer's reasoning. Never add any. A rejected round always gets a *fresh*
  reviewer, never the previous one.
- **Agent-guidance docs never land in an issue PR.** `CLAUDE.md`, `AGENTS.md`,
  `.claude/**` and friends are shared, so an edit inside a fix collides with every
  sibling PR and with the user's own branches. Agents append suggestions to
  `<state>/docnotes/issue-N.md` instead, and one end-of-loop PR lands them together. A
  branch that touches them anyway is bounced into a cheap cleanup before review — do
  not wave it through, and never ask an agent to update those files mid-loop.
- **Issues the classifier put in the same cluster never run concurrently.** The second
  one starts when the first lands. If `next` says `SERIALIZED:`, that is working as
  intended, not a stall.
- **Merge is gated on review-approved AND CI green**, both. If CI cannot run, the
  script says so rather than treating no-checks as green — get an explicit decision
  from the user instead of quietly lowering the bar.
- **Three rejected review rounds parks the issue** (`ARTISANAL_SLOP_MAX_ROUNDS`).

## Verification: who runs what

Three actors can run the test suite; running it in all three is waste. The split gives
each something the others cannot provide:

| Actor | Runs the suite? | Unique contribution |
|---|---|---|
| Implementer | **Yes** — to green | It is how it iterates. Reports the verbatim tail. |
| Reviewer | **No** full rerun | Granular revert/mutation check; adversarial inputs. |
| CI | **Yes** | Every OS and pinned toolchain in the matrix; authoritative. |

Trusting the implementer's *pass/fail report* is safe — CI re-derives it independently
on more platforms. Trusting its *self-assessment of test quality* is not; that is an
agent grading its own homework, and it is exactly the check that has failed in
practice. So the meaningfulness check lives entirely with the reviewer, is done
per-file or per-hunk, and the reviewer's redundant clean full-suite pass is dropped.

## The worktree pool

Agents do not get harness isolation. The script keeps `ARTISANAL_SLOP_MAX_INFLIGHT`
long-lived git worktrees under `<state>/pool/slot-N` and **leases one to each issue for
its whole pipeline** — planner, implementer, reviewer, and any fix agent all share it.
The build cache survives between them, and the slot is reset (tracked changes reverted,
untracked junk cleaned, build artifacts preserved) at each stage boundary.

Because the branch lives in a slot rather than in an agent's head, the script can
rebase siblings itself after a merge: a conflict is a `git rebase` exit code rather
than a guess at GitHub's asynchronously-computed `mergeable` field. A clean rebase is
force-pushed and re-reviewed; a conflicted one goes to a fix agent in the same slot.
Which siblings get that treatment at all is decided first — see below.

## After a merge: who was actually affected

Rebasing every sibling and re-reviewing it is the expensive default, and most of it is
waste. So the script asks a cheaper question first: **does the merged PR touch any file
this sibling touches?**

- **No shared files** → nothing happens. The verdict stands, the running reviewer is
  left alone, and the rebase is deferred to the next idle moment (review approval).
  GitHub tests and merges the PR against current `main` regardless.
- **Shared files** → one cheap `conflict-triage` agent reads the merged diff and each
  sibling's plan and decides, per sibling: `INDEPENDENT` (same file, non-interacting —
  keep the verdict), `REBASE` (today's rebase + fresh review), `REPLAN` (the merge
  invalidated the approach — re-plan now instead of paying an implementation round to
  discover it), or `SERIALIZE` (entangled with another in-flight issue — pause it).

A `SERIALIZE`d issue goes to status `held`: it keeps its slot, branch, and warm cache,
keeps consuming a concurrency slot on purpose, and resumes — rebased — the moment its
blocker reaches a terminal status. `$LOOP record unhold N` releases one by hand.

## Deferred documentation

Agents are forbidden from editing agent-guidance files (`CLAUDE.md`, `AGENTS.md`,
`.claude/**`, …) inside an issue PR. They append what they wanted to say to
`<state>/docnotes/issue-N.md`, and when the queue drains the script hands you one
`STAGE: docs` agent that verifies every note against current `main`, drops the ones
whose issue never landed, and opens a **single** PR attached to no issue. You are then
asked to approve that merge, exactly like an issue PR, and `ACTION: done` follows.

`$LOOP docs list` shows the pending notes; `$LOOP docs run` lands them early if the user
stops the loop before the queue drains.

`$LOOP pool list` shows slots, leases, branches, and sizes. `$LOOP pool reset <k>`
repairs a wedged slot while keeping its cache; `$LOOP pool prune` deletes unleased
slots to reclaim disk (each is a full checkout plus build artifacts).

**Changing the slot count mid-run** — `$LOOP cap` shows it, `$LOOP cap N` changes it,
and it takes effect on the next `$LOOP next`. Slot count and concurrency cap are one
number by design, since a slot is leased per issue.

- **Raising** needs nothing: new slots are created on demand when work is assigned.
- **Lowering never stops anything.** Issues already in flight keep their slots and run
  to completion; the cap only gates *starting* work, so the pipeline drains down to
  the new value. Slots above the cap stay visible to `pool list` and become
  prunable once released.

`ARTISANAL_SLOP_MAX_INFLIGHT` overrides the stored value for a single invocation. If it is
exported, `cap` says so rather than letting it silently mask your change.

## Recovery

If a session is interrupted, `$LOOP init` then `$LOOP reconcile` rebuilds state from
GitHub — open PRs map back to issues via the `issue-N-*` branch convention and `Fixes
#N` in PR bodies. Nothing depends on an agent surviving a restart: every follow-up is a
fresh agent spawned against the branch in its slot, so a recovered issue simply
re-enters review and continues normally.

`$LOOP status` prints the current table at any time; `$LOOP show N` dumps one issue's
full state, blobs, and transition log.

## GitHub gotchas

Cheap to avoid, expensive to debug — read `reference/gotchas.md` in this skill
directory if `gh` behaves surprisingly. The one worth carrying in your head: **closing
keywords match inside code spans and through negation**, so `Fixes`/`Closes`/`Resolves`
must never appear next to any issue number but the intended one.
