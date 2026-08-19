# artisanal-slop

Hand-crafted, small-batch, locally-sourced slop. Point it at a GitHub repo and it
works through the open issues on its own — classifying, planning, implementing,
reviewing, and merging — stopping only to ask whether you actually want a PR merged
or an issue closed.

It is an *issue resolution loop*: a long-running, mostly-unattended pipeline rather
than a single command that does one thing and exits. You start it, it keeps going
until the queue drains or you tell it to stop.

## What it actually does

Each issue moves through a fixed pipeline, and each stage is a separate sub-agent
with its own fresh context:

| Stage | Model | What happens |
| --- | --- | --- |
| classify | Haiku | Ranks the open issues, assigns a severity, writes a one-line summary, and groups issues that touch the same ground into clusters. |
| plan | Opus | Reads the issue and the code, decides whether it's real, and writes a plan — or a comment saying why it isn't. |
| implement | Sonnet | Writes the fix in a dedicated git worktree, gets the test suite green, opens a PR. |
| review | Opus or Sonnet | Independently reviews the PR with *no* knowledge of the plan or the implementer's reasoning. Opus for severity 1–3, Sonnet below that. |
| fix / replan | Sonnet / Opus | Handles review findings, or re-plans when a sibling merge invalidated the approach. |
| docs | Sonnet | One end-of-loop PR collecting agent-guidance doc changes the other stages weren't allowed to make. |

Between those, the loop also polls CI, rebases sibling branches after each merge,
decides which siblings a merge actually affected, and parks issues that keep failing
review.

## Why it's built this way

The decision tree lives in `bin/artisanal-slop`, a ~2,400-line bash state machine, not
in the agent's head. The agent runs `artisanal-slop next`, gets exactly one action
back, does it, records the result, and asks again. It never decides what happens next
and never reads the code itself.

That split is the whole trick. All the state — queue, severities, review round counts,
worktree leases, cluster serialization — sits on disk, so the driving agent's context
stays nearly empty and the loop survives compaction and session restarts. The
expensive thinking happens in short-lived sub-agents that are thrown away afterward.

A few consequences worth knowing about:

- **A pool of persistent git worktrees**, one leased per in-flight issue for its whole
  pipeline, so the build cache stays warm from planning through review. The repo root
  is asserted clean on every step; if an agent writes to it, the loop halts.
- **At most 2 issues in flight** by default. More just multiplies merge conflicts
  between sibling PRs without finishing anything sooner.
- **The reviewer is deliberately kept ignorant.** Its prompt contains the issue and PR
  numbers and nothing else — no plan, no implementation summary. A rejected round
  always gets a brand-new reviewer.
- **Agents never touch `CLAUDE.md`, `AGENTS.md`, or `.claude/**` inside an issue PR.**
  Those files are shared, so an edit collides with every sibling branch. Suggestions
  are queued to a notes file and land in one PR at the end.

## What you're asked about

Approval gates exist at exactly two points: closing an issue without a fix, and
merging a PR. Everything else runs unattended.

Those questions are also non-blocking by design — the loop only asks when the pipeline
is already full or the queue is empty, so work continues on other issues while a
question sits unanswered.

Merging additionally requires review approval **and** green CI, both. If CI can't run
at all, the loop says so instead of quietly treating "no checks" as "passing".

## Requirements

- `bash` 4+, `git`, [`gh`](https://cli.github.com/) (authenticated), and coreutils —
  no standalone `jq`, the driver uses `gh`'s embedded `--jq` for all JSON
- A GitHub repo with issues, run from a clean checkout on the default branch
- Disk space for the worktree pool — each slot is a full checkout plus build artifacts

## Using it

It's user-invoked only (`disable-model-invocation: true`) — Claude will not start this
on its own, which is the correct default for something that opens and merges PRs.

```
/artisanal-slop           # work the whole open-issue queue
/artisanal-slop 42        # start from issue #42
```

Then leave it alone. It'll narrate transitions in one line each and interrupt you for
approvals. Stop it whenever you like; nothing depends on an agent surviving.

## Configuration

The driver reads these from the environment:

| Variable | Default | Effect |
| --- | --- | --- |
| `ARTISANAL_SLOP_MAX_INFLIGHT` | `2` | Concurrent issues, which is also the worktree pool size. |
| `ARTISANAL_SLOP_MAX_ROUNDS` | `3` | Rejected review rounds before an issue is parked for a human. |
| `ARTISANAL_SLOP_STATE_DIR` | per-repo, below | Where state lives. |
| `ARTISANAL_SLOP_POOL_KEEP` | `target node_modules .venv …` | Build artifacts preserved when a slot is reset between stages. |
| `ARTISANAL_SLOP_DEFERRED_DOCS` | `CLAUDE.md AGENTS.md .claude/ …` | Files agents may never edit inside an issue PR. |
| `ARTISANAL_SLOP_ALLOW_DIRTY_ROOT` | `0` | Disables the clean-repo-root assertion. If you need this, something is wrong. |
| `ARTISANAL_SLOP_NO_CLUSTERS` | `0` | Disables serialization of related issues. |

The cap can also be changed mid-run with `artisanal-slop cap N`; lowering it never
stops in-flight work, it just stops new work from starting until the pipeline drains.

## State, inspection, and recovery

State lives in `~/.claude/artisanal-slop/<owner>__<repo>/`. The driver is a normal CLI
you can run yourself while the loop is going:

```bash
LOOP=~/.claude/skills/artisanal-slop/bin/artisanal-slop

$LOOP status         # the current table: every issue and where it is
$LOOP show 42        # one issue's full state, blobs, and transition log
$LOOP summary        # the end-of-run report
$LOOP pool list      # worktree slots, leases, branches, disk usage
$LOOP docs list      # queued agent-guidance notes awaiting the end-of-loop PR
$LOOP reconcile      # rebuild state from GitHub after an interrupted session
```

Recovery is genuinely cheap: open PRs map back to issues through the `issue-N-*`
branch convention and `Fixes #N` in PR bodies, so a killed session picks up by
re-entering review.

## Caveats

This burns tokens continuously and opens real PRs against a real repo. Run it
somewhere you're happy to see a stream of machine-authored branches, and read the
diffs before approving merges — the review stage is an independent check, not a
guarantee.

`reference/gotchas.md` collects the `gh` behaviors that cost the most debugging time.
The one worth knowing up front: GitHub's closing keywords match inside code spans and
through negation, so `Fixes`/`Closes`/`Resolves` must never appear near any issue
number but the intended one.
