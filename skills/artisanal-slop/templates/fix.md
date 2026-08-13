# Task: fix PR #{{PR}} for GitHub issue #{{ISSUE}} in {{REPO}}

Reason you were spawned: **{{REASON}}**

## Your worktree

Work in **`{{WORKTREE}}`** and nowhere else. `cd` there first. It is a persistent git
worktree that already has branch `{{BRANCH}}` checked out at `origin/{{BRANCH}}`, and it
carries a warm build cache from earlier stages — so your first build should be
incremental, not a cold compile.

**Never modify the primary repo checkout.** It must stay clean on `{{DEFAULT_BRANCH}}`;
the loop halts if it is dirty.

## Context

You are a fresh agent picking up work already in progress. An earlier agent
implemented this change; you have its output (the branch and its commits) but not its
reasoning. Reconstruct what you need from primary sources:

- `gh issue view {{ISSUE}} --comments` — what the fix is supposed to accomplish
- `git diff origin/{{DEFAULT_BRANCH}}...HEAD` — what has been done so far
- `gh pr view {{PR}}` — the PR as it stands

The plan this work is based on:

{{FILE:{{BLOB_DIR}}/plan.md}}

## What you must address

{{#REVIEW_FINDINGS}}
An independent reviewer found blocking problems. Address **every** one of them:

{{FILE:{{BODY_FILE}}}}

If a finding faults a specific test for not discriminating, run the targeted revert
for that one test yourself and report what you observed — that one is your job, not
the reviewer's.
{{/REVIEW_FINDINGS}}

{{#CI_FAILURE}}
CI is failing on this PR:

{{FILE:{{BODY_FILE}}}}

Pull the actual logs with `gh run view` / `gh pr checks {{PR}}` before guessing at a
cause. Note that CI runs on more platforms and a pinned toolchain, so a failure that
does not reproduce locally is usually a real platform or toolchain difference, not a
flake — treat it as real unless you can prove otherwise.
{{/CI_FAILURE}}

{{#USER_FEEDBACK}}
The maintainer reviewed the PR and asked for changes before merging. Their feedback is
authoritative:

{{FILE:{{BODY_FILE}}}}
{{/USER_FEEDBACK}}

{{#DEFERRED_DOCS}}
{{FILE:{{BODY_FILE}}}}

Agent-guidance files are never edited inside an issue PR. They are shared, so every such
edit conflicts with sibling PRs and with the maintainer's own branches — and clearing
that conflict costs a stopped reviewer and a restarted implementer. The full deferred
set is `{{DEFERRED_DOCS}}`.

Do this, and nothing else:

1. Restore each listed file to its state on the default branch:
   `git checkout origin/{{DEFAULT_BRANCH}} -- <path>` (for a file this PR *added*,
   `git rm --cached` it and delete it instead).
2. Move the intent you are removing into `{{DOCNOTE_FILE}}` — **append** to that file:
   which doc, the wording you wanted, and why. It is not lost; one end-of-loop PR
   applies every note like it together.
3. Confirm nothing else changed: `git diff origin/{{DEFAULT_BRANCH}}...HEAD --name-only`
   must list no path from the deferred set, and the rest of the change must be intact.
4. Commit and push to the same branch.

Leave the actual fix alone. This is a scope correction, not a re-implementation.
{{/DEFERRED_DOCS}}

{{#REBASE_CONFLICT}}
{{FILE:{{BODY_FILE}}}}

Rebase `{{BRANCH}}` onto `origin/{{DEFAULT_BRANCH}}` and resolve the conflicts. Then do
the part that matters more than the mechanical resolution: **reassess whether the fix
is still correct against the new `{{DEFAULT_BRANCH}}`.** The merged change may have
altered, moved, or already fixed the code this change depends on.

If the merged change invalidated the approach rather than merely colliding with it,
**stop and say so** — reply `PREMISE CHANGED — <what was invalidated>` and do not force
the old plan through. Re-planning is cheaper than an incorrect merge.

Push with `git push --force-with-lease` once the rebase is clean.
{{/REBASE_CONFLICT}}

## Then

- Re-run every verification command the plan names, until they all pass.
- Commit and push to the same PR branch — do **not** open a new PR.
{{#DOCS_DEFERRED}}
- Do not create or edit `{{DEFERRED_DOCS}}` — they are shared files that conflict with
  every sibling PR. Append any suggestion for them to `{{DOCNOTE_FILE}}` instead; one
  end-of-loop PR lands them all.
{{/DOCS_DEFERRED}}
- Do not write `Fixes`/`Closes`/`Resolves` next to any issue number other than
  #{{ISSUE}}, in any commit message or comment. GitHub's linkifier matches inside code
  spans and through negation.

## Report back

What you changed, why, and the verbatim tail of the verification output showing the
checks pass. If you could not resolve it, say so plainly rather than pushing a
speculative fix.
