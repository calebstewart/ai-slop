# Task: implement the fix for GitHub issue #{{ISSUE}} in {{REPO}}

Issue title: {{TITLE}}

Everything you need is below — a planner already investigated this issue and wrote the
plan. Follow it. You should not need to ask any questions; if the plan is genuinely
wrong or impossible, say so in your report rather than improvising a different fix.

## Your worktree

Work in **`{{WORKTREE}}`** and nowhere else. `cd` there first. It is a persistent git
worktree, currently detached at `origin/{{DEFAULT_BRANCH}}`, and the planner already
warmed its build cache — your first build should be incremental, not a cold compile of
every dependency. Do not create your own worktree or clone.

**Never modify the primary repo checkout.** It must stay clean on `{{DEFAULT_BRANCH}}`;
the loop halts if it is dirty.

## The issue

Run `gh issue view {{ISSUE}} --comments` and read it in full before you start.

## The plan

{{FILE:{{BLOB_DIR}}/plan.md}}

## How to work

1. In your worktree, `git fetch origin` and branch from `origin/{{DEFAULT_BRANCH}}` as
   `issue-{{ISSUE}}-<short-slug>`.
2. Implement the plan and add the planned tests, following the repo's existing test
   conventions.
3. Run every verification command the plan names, and iterate until they all pass.
4. **Do not run the revert/meaningfulness check on your own tests.** An independent
   reviewer does that, and an agent grading its own test quality is the least reliable
   version of that check. Get the suite green and report it.
   *Exception:* if a previous review round faulted one specific test for not
   discriminating, run the targeted revert for that one test and report what you saw.
5. Commit with a clear message ending in the standard co-author trailer, push the
   branch to `origin`, and open a PR with `gh pr create`. The body must explain the
   change and contain `Fixes #{{ISSUE}}` so the issue auto-closes on merge.

{{#DOCS_DEFERRED}}
## ⚠️ Agent-guidance docs are deferred

Do not create or edit these files in this PR: `{{DEFERRED_DOCS}}`. They are shared, so an
edit here conflicts with every sibling PR and with the maintainer's own branches, and
clearing that conflict costs a stopped reviewer and a restarted implementer. If your
work implies one of them should change, **append** the suggestion to `{{DOCNOTE_FILE}}`
— which file, the wording you want, and why — and carry on. A single end-of-loop PR
applies every note together. A branch that touches them is bounced back to you for
cleanup before it can reach review.

{{/DOCS_DEFERRED}}

## ⚠️ Closing-keyword hazard

Never write a closing keyword — `Fixes`, `Closes`, `Resolves` — next to **any** issue
number other than #{{ISSUE}}. Not in prose, not inside backticks, not while explaining
that you are *not* using one. GitHub's linkifier matches the string regardless of code
formatting or surrounding negation: writing ``uses `Refs #10`, not `Fixes #10` `` has
auto-closed issue #10 on merge. To reference another issue, use a bare `#NN` with no
keyword in front of it.

## Report back

- The PR number and URL.
- What you changed and why, briefly.
- The verbatim tail of the test/lint output proving the checks pass.

If you hit an unresolvable blocker, say so plainly and stop — nothing unverified gets
merged, so a clear failure report is far more useful than a speculative fix.

## Staying in sync

You may receive a message mid-run telling you that another PR merged to
`{{DEFAULT_BRANCH}}`. When that happens, `git fetch origin` and rebase onto
`origin/{{DEFAULT_BRANCH}}` immediately, before continuing — absorbing the change early
is much cheaper than discovering the conflict at PR time. If the merged change overlaps
or invalidates the approach in your plan, say so explicitly in your reply instead of
forcing the plan through.

You are the only agent that receives these notices mid-run: once you report back, the
loop rebases your slot itself rather than messaging you.
