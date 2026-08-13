# Task: land the deferred agent-guidance doc updates for {{REPO}}, in one PR

Throughout this run, agents were forbidden from editing agent-guidance files inside an
issue PR — `{{DEFERRED_DOCS}}` — because every issue PR touching them collides with
every other one and with the maintainer's own branches. Instead each agent wrote down
what it thought should change. You are the one pass that applies those notes, together,
on a branch attached to no issue.

{{NOTE_COUNT}} note file(s) were collected.

## Your worktree

Work in **`{{WORKTREE}}`** and nowhere else. `cd` there first. It is a persistent git
worktree, currently detached at `origin/{{DEFAULT_BRANCH}}`.

**Never modify the primary repo checkout.** It must stay clean on `{{DEFAULT_BRANCH}}`;
the loop halts if it is dirty.

## The notes

Each note is stamped with the issue it came from and what happened to that issue. A note
from an issue that ended `parked`, `failed`, or `skipped` describes work that **never
landed** — its suggestion is usually wrong now.

{{FILE:{{MANIFEST_FILE}}}}

## How to work

1. `git fetch origin` and branch from `origin/{{DEFAULT_BRANCH}}` as `{{BRANCH}}`.
2. **Verify every suggestion against the code as it is now**, not as the note assumed.
   Read the file the note wants to change and the code it describes. Drop any note whose
   premise did not land, that duplicates guidance already present, or that documents a
   behavior you cannot find in the repo. Say in your report what you dropped and why.
3. Merge overlapping suggestions into single coherent edits. Three notes asking for a
   line about the same build command are one edit, not three.
4. Match the surrounding document — its voice, structure, and level of detail. These
   files are read by agents on every future task, so favor a short, load-bearing
   sentence in the right section over a new section restating what is already implied.
   Do not restructure or "improve" documents beyond what the notes call for.
5. Keep the change to `{{DEFERRED_DOCS}}`. If a note asks for something else — a code
   change, a README rewrite, a CI tweak — leave it out and name it in your report; it
   belongs in an issue, not here.
6. Commit with a clear message ending in the standard co-author trailer, push, and open
   **one** PR with `gh pr create`. The body should list, per file, what changed and
   which issue prompted it (bare `#NN` references).

## ⚠️ This PR fixes no issue

Never write a closing keyword — `Fixes`, `Closes`, `Resolves` — next to any issue number
in the branch, commits, PR title, or PR body. Not in prose, not inside backticks, not
while explaining that you are *not* closing anything: GitHub's linkifier matches
regardless of code formatting or surrounding negation, and this PR closing someone's
open issue would be a silent, confusing bug. Reference issues as bare `#NN` only.

## Report back

Your final message must begin with one of these on its own line:

    DOCS_PR: <pr-number>
    URL: <pr-url>

or, if after verification nothing was left worth landing:

    NONE
    REASON: <one line>

Then, briefly: what you applied, and what you dropped with the reason for each.
