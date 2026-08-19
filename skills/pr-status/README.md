# pr-status

Triage of your own open pull requests. It answers the three questions worth asking on a
Monday morning: what is blocked on me, what is waiting on somebody else, and what has
quietly rotted since I last looked.

Built for the start of a day or week, or the morning after PTO, when the honest answer to
"what was I doing?" is spread across dozens of PRs in several orgs.

## What it does

One paginated GraphQL search collects every matching open PR. PRs whose checks are red get
a second lookup for the *names* of the failing checks, so the report says
`ci/circleci: coverage` rather than "something failed". Each PR then lands in exactly one
bucket, most urgent first:

| Bucket | Meaning |
| --- | --- |
| Needs your action | Merge conflicts, failing checks, or changes requested. |
| Ready to merge | Approved, green, and cleanly mergeable — the cheapest work to close out. |
| No reviewer assigned | Nobody has been asked. These stall silently and are what PTO tends to bury. |
| Waiting on others | Review requested, nothing blocking on your end. |
| Drafts | Collapsed to a count, plus any that have gone stale. |

Staleness is tiered at 7 / 14 / 30 days without activity.

## Scoping

Employer and personal work in one list is noise, so scope is settled before anything runs:
`--org NAME`, `--user NAME`, or `--repo OWNER/NAME`. Invoked from inside a repository, the
skill offers to narrow to that repo, its owning org, or everything.

## Drafts and the review queue

Drafts are counted but not detailed by default — the focus is ready-for-review work, while
still surfacing in-progress branches that have stopped moving so they don't get lost.
`--include-drafts` expands them; `--drafts-only` shows nothing else.

`--review-requested` flips to the inbound queue: PRs waiting on *your* review. The buckets
change with it, because conflicts and failing checks are the author's problem there, not
yours — those sort under "blocked on the author" instead of climbing to the top of your list.

## Things it gets right that are easy to get wrong

- **Bot reviews are not reviews.** Greptile and friends leave `COMMENTED` reviews that read
  as activity. They're tracked separately, so a PR with only bot comments still counts as
  needing a human.
- **`updatedAt` lies.** A bot comment refreshes it, making an untouched PR look active. The
  report also shows days since the last *commit*; when they disagree, the commit age is the
  real signal.
- **Lazily-computed mergeability.** GitHub often returns `UNKNOWN` on first ask and resolves
  it on a later run, so counts can shift between back-to-back runs. Unknown is reported as
  unknown rather than as a clean merge.
- **Comment bodies are a context bonfire.** `gh pr view --json comments` dumps every full
  comment; the skill is told to slice specific fields instead.

## Using it

`/pr-status`, optionally with an org or `--drafts`. It's also model-invoked, so asking what's
outstanding on your PRs is usually enough.

Needs `gh` (authenticated) and `python3`. Standard library only — no dependencies to install.
An unscoped run over a large account takes roughly half a minute, since search pages are
cursor-dependent and can't be fetched in parallel.
