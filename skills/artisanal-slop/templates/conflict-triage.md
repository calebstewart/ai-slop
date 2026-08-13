# Task: decide what PR #{{MERGED_PR}} merging means for the work still in flight

PR #{{MERGED_PR}} (issue #{{MERGED_ISSUE}}) just squash-merged to `{{DEFAULT_BRANCH}}` in
{{REPO}}. Issue(s) **{{SIBLINGS}}** have changes in flight that touch at least one of the
same files.

Every sibling that shares no file with the merged change was already resolved without
you. Your job is the remaining judgment call, and it is worth making carefully: the
default reaction to a merge is to rebase the sibling, throw away its review, and review
it again — sometimes only to discover, an implementation round later, that the merged
change invalidated the whole approach. Deciding correctly here is what avoids paying for
that twice.

## Read-only

You have no worktree. Inspect with `gh` and by reading files in the checkout you are
started in. **Do not modify, stage, commit, or push anything, anywhere.**

## What to look at

- `gh pr view {{MERGED_PR}}` and `gh pr diff {{MERGED_PR}}` — what actually changed, not
  what the title claims.
- For each sibling below: `gh pr diff <its PR>` where it has one, plus its plan.
- The code around the shared files, as needed to tell whether the two changes interact
  or merely live in the same file.

## The siblings

{{FILE:{{INPUT_FILE}}}}

## The decision, per sibling

Sharing a file is not the same as interacting. Two functions in one file, one renamed
constant nobody else reads, edits in different modules of the same crate — those are
independent, and treating them as conflicts is exactly the waste this step exists to
prevent. Judge the *semantics*, not the path list.

- **`INDEPENDENT`** — the changes touch the same file but do not interact: different
  functions, different call paths, no shared assumption. The sibling's review verdict
  still holds and it is not re-reviewed. This is a real and common answer; use it
  whenever it is true.
- **`REBASE`** — they interact enough that a verdict formed before the merge cannot be
  trusted: the merged change moved, renamed, or altered code the sibling builds on, or
  the combined behavior needs a fresh look. The sibling is rebased and re-reviewed.
- **`REPLAN`** — the merged change invalidated the sibling's *approach*: it already
  fixed the same defect, removed the code the plan targets, or changed the design the
  plan assumed. Say so now rather than letting an implementer rediscover it. Also use
  this if the merged change means the sibling's issue no longer needs fixing.
- **`SERIALIZE blocked-by #<issue>`** — this sibling is entangled with **another
  in-flight issue** (not the merged one), such that finishing them concurrently means
  one of them gets rebased, re-fixed, and re-reviewed for nothing. The named issue must
  be one still in flight. The sibling is paused, keeping its branch, and resumes
  automatically — rebased — once that issue lands. Use this sparingly and only when the
  entanglement is concrete.

When you are genuinely torn between `INDEPENDENT` and `REBASE`, choose `REBASE`: a
needless review costs tokens, a missed interaction costs a bad merge.

## Output

Write exactly one line per sibling to `{{OUT_FILE}}`, and nothing else in the file:

    <issue>: <DECISION> [blocked-by #<issue>] — <one line of concrete reasoning>

For example:

    41: INDEPENDENT — both edit src/parse.rs but #41 only touches the header path, untouched by #{{MERGED_PR}}.
    52: REPLAN — #{{MERGED_PR}} deleted the retry wrapper #52's plan intends to patch.

Your final message: the path `{{OUT_FILE}}` and a one-line summary. Keep it short — the
file is the deliverable.
