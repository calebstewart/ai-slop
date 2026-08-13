# Task: re-plan GitHub issue #{{ISSUE}} in {{REPO}}

Issue title: {{TITLE}}

A plan for this issue already existed. Something changed underneath it, and you are
producing a **revised** plan — starting from the current state of the code, not from
the assumption that the earlier work was right.

{{#FROM_PREMISE_CHANGE}}
## What changed

PR #{{MERGED_PR}} merged to `{{DEFAULT_BRANCH}}` while this issue's fix was in flight,
and the implementer reports that the merged change altered the premise of the original
plan. An existing branch and PR (#{{PR}}) may already carry a partial implementation.

Read the merged change first — `gh pr view {{MERGED_PR}}` and
`gh pr diff {{MERGED_PR}}` — then re-examine the issue against current
`origin/{{DEFAULT_BRANCH}}`. It is entirely possible the merged change resolved this
issue outright; say so if it did.

Note that any prior review approval on PR #{{PR}} is void.
{{/FROM_PREMISE_CHANGE}}

{{#FROM_DECLINED_CLOSE}}
## What changed

Triage previously concluded this issue should be closed, and the maintainer disagreed.
Their feedback is authoritative — treat the earlier verdict as wrong and work out what
was missed.

Maintainer feedback:

{{FILE:{{FEEDBACK_FILE}}}}
{{/FROM_DECLINED_CLOSE}}

## The earlier work ({{PRIOR_LABEL}})

{{FILE:{{PRIOR_FILE}}}}

## Your worktree

Work in **`{{WORKTREE}}`** and nowhere else. `cd` there first. It is the persistent git
worktree reserved for this issue, with a warm build cache from the earlier attempt.

**Never modify the primary repo checkout.** It must stay clean on `{{DEFAULT_BRANCH}}`;
the loop halts if it is dirty.

## What to produce

Follow the same investigation and output contract as a first-pass plan: read
`gh issue view {{ISSUE}} --comments`, read the repo's `CLAUDE.md` / `CONTRIBUTING.md` /
CI workflows for build, test, and lint commands (including any required wrapper prefix)
and documented constraints, and reproduce in your own worktree before concluding
anything. Do not push and do not open a PR.

{{#DOCS_DEFERRED}}
## Agent-guidance docs are deferred

Read them freely — never plan a change to them: `{{DEFERRED_DOCS}}`. They are shared, so
an edit inside an issue PR conflicts with sibling PRs and with the maintainer's own
branches. If your investigation turns up something one of them should say, **append** it
to `{{DOCNOTE_FILE}}` — which file, the wording you want, and why. One end-of-loop PR
applies every note together. Exception: an issue whose *subject* is one of those files;
then say `DOCS_EXEMPT: yes` in your final message.
{{/DOCS_DEFERRED}}

Return exactly one verdict, with the deliverable written to a file under
`{{BLOB_DIR}}/`:

- **`VALID`** → a revised, fully self-contained plan at `{{BLOB_DIR}}/plan.md`: root
  cause with `file:line`, the change file by file, constraints that must not break, a
  test plan matching the repo's conventions, and the exact verification commands. Call
  out explicitly what differs from the earlier plan and why, since an implementation may
  already be partly built against the old one.
- **`INVALID` / `ALREADY-FIXED` / `WONT-FIX`** → a draft closing comment at
  `{{BLOB_DIR}}/close-comment.md` with concrete evidence.
- **`NEEDS-HUMAN`** → a maintainer-addressed write-up at `{{BLOB_DIR}}/needs-human.md`
  covering your research, the candidate approaches and their trade-offs, your
  recommendation or explicit lack of one, and the exact decision needed.

Final message: the verdict word on its own line, then `CATEGORY:` (1-5, your corrected
severity), the relevant `PLAN_FILE:` / `COMMENT_FILE:` / `WRITEUP_FILE:` path, and a
one-line `SUMMARY:`.
