---
name: pr-status
description: Reviews your open GitHub pull requests with the gh CLI and reports each one's state — reviews, failing checks, merge conflicts, and staleness. Use when the user asks about their open PRs, pending contributions, outstanding or in-progress work, what needs attention, a start-of-day or start-of-week review, or catching up after PTO.
argument-hint: "[org] [--drafts] [--review-requested]"
allowed-tools: Bash, AskUserQuestion, Read
---

# Reviewing open pull requests

Triage the user's open GitHub PRs into what needs their action, what is waiting on
someone else, and what is going stale. Read-only: nothing here writes to GitHub.

`scripts/pr_status.py` (resolve it against this skill's own directory) does the
collection, staleness math, and formatting. Run it — do not reimplement its `gh`
calls inline, and do not re-fetch PRs it already reported on.

## 1. Resolve scope first

Scope decides whether employer and personal work get mixed together, so settle it
before running anything.

- **User named a scope** ("my huntresslabs PRs", "personal repos", "this repo") → use it,
  ask nothing.
- **Otherwise, if the session is inside a repo** → run
  `gh repo view --json nameWithOwner -q .nameWithOwner`, then use `AskUserQuestion` to
  offer: this repo only / its owning org / everything. This is the common case for a
  focused check-in.
- **Not in a repo and nothing specified** → run unscoped.

`gh api user/orgs --jq '.[].login'` lists the orgs available for scoping.

## 2. Run the script

```bash
python3 <skill-dir>/scripts/pr_status.py [--org NAME | --user NAME | --repo OWNER/NAME]
```

| Flag | Use when |
|---|---|
| `--org NAME` / `--user NAME` / `--repo OWNER/NAME` | scoping to employer / personal / one repo |
| `--include-drafts` | the user wants in-progress work in full detail |
| `--drafts-only` | reviewing only unfinished work |
| `--review-requested` | the user's inbound review queue instead of their own PRs |
| `--warn-days` / `--stale-days` / `--abandoned-days` | override the 7 / 14 / 30-day tiers |
| `--exclude-archived` | drop PRs in archived repos (unactionable noise) |
| `--json` | further filtering or counting is needed |

An unscoped run over a large account takes ~30 seconds (search pages are sequential and
failing PRs get an extra lookup). That is normal — let it finish rather than retrying.

## 3. Report on it

Summarize; do not paste the script's output back verbatim.

1. Lead with **what needs their action**, naming the specific blocker per PR — which
   check failed, which reviewer is sitting on it, whether it conflicts.
2. Then anything **ready to merge**, since that is the cheapest work to close out.
3. Then PRs with **no reviewer assigned** — these stall silently and are the most
   common thing lost over PTO.
4. Then what is **waiting on others**, and the **stale** tail, oldest first.
5. Close with the **draft count**, calling out any drafts past the warn tier.

Group by repo when one repo dominates the list. Suggest a concrete next step for the top
few PRs rather than restating their state. If a bucket is empty, say so in a clause and
move on.

## Interpreting the data

- **Drafts are excluded from detail by default** and reported as a count plus any that
  have gone stale, so in-progress work is never silently dropped.
- **Bot reviews are not human reviews.** Greptile/Copilot leave `COMMENTED` reviews that
  look like activity; the script tracks them separately. A PR with only bot reviews still
  needs a human, so treat it as unreviewed.
- **Staleness tiers come from `updatedAt`, which bots inflate.** A bot comment makes an
  untouched PR look fresh, so the report also shows days since the last *commit*. When the
  two disagree, trust the commit age as the real progress signal.
- **`mergeability unknown` is not "clean."** GitHub computes mergeability lazily; it
  resolves on a later run. Say it is unknown rather than implying the PR merges cleanly.
- **In `--review-requested` mode the buckets shift**: conflicts and failing checks are the
  *author's* problem, so those PRs sort under "blocked on the author" and should be
  deprioritized in favor of ones actually ready to read.
- GitHub search returns at most 1000 results; the script says so explicitly if the cap is
  hit. Narrow the scope instead of assuming the list is complete.

## When digging into one PR

Fetch only what is missing — the script already has state, reviews, checks, and size.

Never pass `comments` or `body` to `gh pr view --json`: it dumps every full comment body
and burns a large amount of context for almost no signal. To read discussion, select
specific fields and slice, e.g.
`gh pr view N --repo O/R --json comments -q '.comments[-3:][].body'`.

Useful follow-ups: `gh pr checks N --repo O/R` for full check status (it **exits non-zero
when checks fail** — that is data, not an error), and `gh pr diff N --repo O/R --name-only`
for scope without the patch.

## Follow-ups to offer

Re-run with `--include-drafts` for in-progress work, `--org`/`--user` to separate employer
from personal, or `--review-requested` for the inbound review queue.
