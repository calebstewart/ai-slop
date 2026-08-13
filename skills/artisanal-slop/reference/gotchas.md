# GitHub gotchas

Failure modes this loop has actually hit. Each is cheap to avoid and expensive to
debug from symptoms.

## Closing keywords match inside code spans and through negation

Writing ``uses `Refs #10`, not `Fixes #10` `` in a PR body auto-closed issue #10 on
merge. GitHub's linkifier scans the raw text: backticks do not protect it, and the
surrounding "not" means nothing to it.

Never put `Fixes` / `Closes` / `Resolves` next to any issue number except the one the
PR should close. To reference another issue, use a bare `#NN` with no keyword in front.

Recovery: `gh issue reopen N --comment "…"` explaining the cause and what genuinely
remains open.

## Forks have Actions disabled by default

Symptom: `actions/permissions` reports `enabled: true`, workflows show `state: active`,
triggers look correct — and `gh run list` is **empty for the whole repo**, on every
branch. That combination is the fork signature.

There is no REST endpoint for it. It needs a one-time click on the Actions tab ("I
understand my workflows, go ahead and enable them").

Enabling does **not** retroactively fire `pull_request` events on already-open PRs.
Replay with `gh pr close N && gh pr reopen N`, or push an empty commit.

`artisanal-slop ci` reports `RESULT: NONE` for this case rather than treating an empty
check list as green.

## An agent that ignores its assigned worktree

`isolation: "worktree"` is enforced by the harness. A pooled slot is communicated by a
*prompt instruction*, which is not. An agent that ignores it will work in whatever
directory it started in — usually the repo root.

`assert_root_clean()` runs on every `next` and `record` and halts the loop if the root
has uncommitted changes. If it fires: find which agent did it, `git -C <root> stash` or
discard the changes, and check whether that agent's work needs redoing in its slot.
`ARTISANAL_SLOP_ALLOW_DIRTY_ROOT=1` overrides the check, but the root being dirty means
some agent's output landed somewhere the loop is not tracking.

## `gh pr merge --delete-branch` fails when an agent worktree holds the branch

Error: `cannot delete branch 'X' used by worktree at …`, non-zero exit. The merge and
the **remote** branch deletion both succeeded; only local cleanup failed. Harmless.

Verify with `gh pr view N --json state` rather than trusting the exit code — which is
what `artisanal-slop` does.

## `mergeable` is `UNKNOWN` right after a merge

GitHub recomputes mergeability asynchronously. Polling immediately after a merge
reports `UNKNOWN` for sibling PRs and tells you nothing.

`artisanal-slop` no longer asks. Because each issue holds a persistent worktree, the
post-merge fanout runs a real `git rebase` in the slot and reads its exit code, which
is both immediate and authoritative. Only a *live* implementer — one whose slot the
script must not touch mid-run — still gets a message instead.

## A prior review approval never survives a rebase

If a sibling merge conflicts an already-approved PR, the approval is void — the code
the fix depends on may have changed underneath it. The PR goes back to `implementing`,
the in-flight reviewer is stopped, and the fix is re-reviewed from scratch after the
rebase. If the implementer reports the merged change invalidated the approach, it goes
back to a *planner* first, not straight to review.
