#!/usr/bin/env python3
"""Triage open GitHub pull requests via the `gh` CLI.

Collects every matching open PR in one paginated GraphQL search, enriches the
failing ones with their failing check names, sorts each PR into a single
priority bucket, and prints a compact report.

Requires only the Python standard library and an authenticated `gh`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# GitHub returns HTTP 502 when a search selecting `statusCheckRollup` asks for
# 50 nodes per page. 25 is verified stable; do not raise it.
PAGE_SIZE = 25

# GitHub's search API refuses to paginate past 1000 results.
SEARCH_RESULT_CAP = 1000

# Bound the extra `gh pr checks` calls made for PRs with failing rollups.
CHECK_WORKERS = 6
MAX_NAMED_CHECKS = 3

QUERY = """
query($q: String!, $after: String, $size: Int!) {
  search(query: $q, type: ISSUE, first: $size, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number title url isDraft createdAt updatedAt
        repository { nameWithOwner }
        mergeable mergeStateStatus reviewDecision
        additions deletions changedFiles
        author { login }
        reviewRequests(first: 10) {
          totalCount
          nodes { requestedReviewer {
            __typename
            ... on User { login }
            ... on Team { name }
            ... on Bot { login }
          } }
        }
        latestReviews(first: 10) {
          nodes { state submittedAt author { login __typename } }
        }
        commits(last: 1) {
          nodes { commit { committedDate statusCheckRollup { state } } }
        }
      }
    }
  }
}
"""

AUTHOR_BUCKETS = [
    ("action", "Needs your action"),
    ("ready", "Ready to merge"),
    ("no_reviewer", "No reviewer assigned"),
    ("waiting", "Waiting on others"),
]

# In review-requested mode the same signals mean something different: conflicts
# and failing checks are the *author's* problem, so they drop down the list
# rather than becoming your action item.
REVIEW_BUCKETS = [
    ("review_now", "Ready for your review"),
    ("blocked_on_author", "Blocked on the author"),
]


def die(message: str) -> None:
    print(f"pr_status: {message}", file=sys.stderr)
    sys.exit(1)


def run_gh(args: list[str], *, tolerate_failure: bool = False) -> str:
    """Run a gh command and return stdout.

    `gh pr checks` exits non-zero when checks are failing, which is a normal
    result here rather than an error, so callers can opt into tolerating a
    non-zero exit as long as stdout still parses.
    """
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False
        )
    except OSError as exc:  # pragma: no cover - depends on local environment
        die(f"could not execute gh: {exc}")
    if proc.returncode != 0 and not (tolerate_failure and proc.stdout.strip()):
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        hint = detail[-1] if detail else f"exit status {proc.returncode}"
        die(f"gh {' '.join(args[:2])} failed: {hint}")
    return proc.stdout


def build_search_query(opts: argparse.Namespace) -> str:
    terms = ["is:pr", "is:open"]
    if opts.review_requested:
        terms.append(f"review-requested:{opts.author}")
    else:
        terms.append(f"author:{opts.author}")
    if opts.org:
        terms.append(f"org:{opts.org}")
    if opts.user:
        terms.append(f"user:{opts.user}")
    if opts.repo:
        terms.append(f"repo:{opts.repo}")
    if opts.exclude_archived:
        terms.append("archived:false")
    return " ".join(terms)


def fetch_pull_requests(query: str) -> tuple[list[dict], int]:
    """Page through the search, returning (nodes, total reported by GitHub)."""
    nodes: list[dict] = []
    cursor: str | None = None
    total = 0
    while True:
        args = [
            "api", "graphql",
            "-F", f"q={query}",
            "-F", f"size={PAGE_SIZE}",
            "-f", f"query={QUERY}",
        ]
        if cursor:
            args += ["-F", f"after={cursor}"]
        payload = json.loads(run_gh(args))
        if payload.get("errors"):
            die(f"GraphQL error: {payload['errors'][0].get('message', 'unknown')}")
        search = payload["data"]["search"]
        total = search["issueCount"]
        # Non-PR results decode as empty objects; drop them.
        nodes.extend(n for n in search["nodes"] if n)
        page = search["pageInfo"]
        if not page["hasNextPage"] or len(nodes) >= SEARCH_RESULT_CAP:
            break
        cursor = page["endCursor"]
    return nodes, total


def rollup_state(pr: dict) -> str | None:
    commits = (pr.get("commits") or {}).get("nodes") or []
    if not commits:
        return None
    rollup = (commits[0].get("commit") or {}).get("statusCheckRollup")
    return rollup.get("state") if rollup else None


def last_commit_date(pr: dict) -> str | None:
    commits = (pr.get("commits") or {}).get("nodes") or []
    if not commits:
        return None
    return (commits[0].get("commit") or {}).get("committedDate")


def age_days(timestamp: str | None, now: datetime) -> int | None:
    if not timestamp:
        return None
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return max(0, (now - moment).days)


def reviewer_names(pr: dict) -> list[str]:
    names = []
    for node in (pr.get("reviewRequests") or {}).get("nodes") or []:
        reviewer = node.get("requestedReviewer") or {}
        name = reviewer.get("login") or reviewer.get("name")
        if name:
            names.append(f"@{name}" if reviewer.get("__typename") != "Team" else name)
    return names


def split_reviews(pr: dict) -> tuple[list[dict], list[dict]]:
    """Separate human reviews from bot reviews.

    Review bots (Greptile, Copilot, ...) leave COMMENTED reviews that must not
    be mistaken for a human having looked at the PR.
    """
    human, bot = [], []
    for review in (pr.get("latestReviews") or {}).get("nodes") or []:
        author = review.get("author") or {}
        (bot if author.get("__typename") == "Bot" else human).append(review)
    return human, bot


def fetch_failing_checks(prs: list[dict]) -> None:
    """Attach failing check names to PRs whose rollup reports FAILURE."""
    targets = [pr for pr in prs if pr["_rollup"] == "FAILURE"]
    if not targets:
        return

    def lookup(pr: dict) -> None:
        raw = run_gh(
            [
                "pr", "checks", str(pr["number"]),
                "--repo", pr["repository"]["nameWithOwner"],
                "--json", "name,state,link,bucket",
            ],
            tolerate_failure=True,
        )
        try:
            checks = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return
        pr["_failing_checks"] = [
            c["name"] for c in checks if c.get("bucket") == "fail"
        ]

    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as pool:
        list(pool.map(lookup, targets))


def classify(pr: dict, review_mode: bool = False) -> str:
    if pr["isDraft"]:
        return "draft"
    if review_mode:
        if pr["mergeable"] == "CONFLICTING" or pr["_rollup"] == "FAILURE":
            return "blocked_on_author"
        return "review_now"
    if (
        pr["mergeable"] == "CONFLICTING"
        or pr["_rollup"] == "FAILURE"
        or pr["reviewDecision"] == "CHANGES_REQUESTED"
    ):
        return "action"
    if (
        pr["reviewDecision"] == "APPROVED"
        and pr["_rollup"] in (None, "SUCCESS")
        and pr["mergeStateStatus"] == "CLEAN"
    ):
        return "ready"
    if not pr["_reviewers"] and not pr["_human_reviews"]:
        return "no_reviewer"
    return "waiting"


def tier(days: int | None, opts: argparse.Namespace) -> str | None:
    if days is None:
        return None
    if days >= opts.abandoned_days:
        return "abandoned"
    if days >= opts.stale_days:
        return "stale"
    if days >= opts.warn_days:
        return "aging"
    return None


def annotate(prs: list[dict], opts: argparse.Namespace, now: datetime) -> None:
    for pr in prs:
        pr["_rollup"] = rollup_state(pr)
        pr["_failing_checks"] = []
        pr["_reviewers"] = reviewer_names(pr)
        pr["_human_reviews"], pr["_bot_reviews"] = split_reviews(pr)
        pr["_idle_days"] = age_days(pr["updatedAt"], now)
        pr["_commit_days"] = age_days(last_commit_date(pr), now)
        pr["_tier"] = tier(pr["_idle_days"], opts)


def describe(pr: dict) -> list[str]:
    """Human-readable reasons this PR is where it is."""
    notes = []

    if pr["mergeable"] == "CONFLICTING":
        notes.append("merge conflicts")
    elif pr["mergeable"] == "UNKNOWN":
        notes.append("mergeability unknown")
    elif pr["mergeStateStatus"] == "BEHIND":
        notes.append("behind base branch")
    elif pr["mergeStateStatus"] == "BLOCKED":
        notes.append("merge blocked")

    if pr["_rollup"] == "FAILURE":
        names = pr["_failing_checks"][:MAX_NAMED_CHECKS]
        extra = len(pr["_failing_checks"]) - len(names)
        label = ", ".join(names) if names else "see PR"
        if extra > 0:
            label += f", +{extra} more"
        notes.append(f"checks failing ({label})")
    elif pr["_rollup"] == "PENDING":
        notes.append("checks running")
    elif pr["_rollup"] is None:
        notes.append("no checks")

    decision = pr["reviewDecision"]
    if decision == "CHANGES_REQUESTED":
        notes.append("changes requested")
    elif decision == "APPROVED":
        notes.append("approved")
    elif not pr["_human_reviews"]:
        if pr["_reviewers"]:
            notes.append(f"awaiting review from {', '.join(pr['_reviewers'][:3])}")
        else:
            notes.append("no reviewer requested")

    if pr["_bot_reviews"] and not pr["_human_reviews"]:
        notes.append(f"{len(pr['_bot_reviews'])} bot review(s) only")

    if pr["_tier"]:
        notes.append(pr["_tier"].upper())

    return notes


def format_pr(pr: dict) -> str:
    repo = pr["repository"]["nameWithOwner"].split("/")[-1]
    idle = pr["_idle_days"]
    commit = pr["_commit_days"]
    age = f"{idle}d idle" if idle is not None else "age ?"
    if commit is not None and commit != idle:
        age += f"/{commit}d since commit"
    size = f"+{pr['additions']}-{pr['deletions']} in {pr['changedFiles']}f"
    head = f"  {repo}#{pr['number']}  {age}  {size}  {'; '.join(describe(pr))}"
    return f"{head}\n      {pr['title']}\n      {pr['url']}"


def sort_key(pr: dict) -> tuple:
    return (-(pr["_idle_days"] or 0), pr["repository"]["nameWithOwner"], pr["number"])


def report(prs: list[dict], total: int, opts: argparse.Namespace, scope: str) -> None:
    drafts = [p for p in prs if p["_bucket"] == "draft"]
    active = [p for p in prs if p["_bucket"] != "draft"]

    if opts.review_requested:
        subject, active_label = "PRs awaiting your review", "non-draft"
    else:
        subject, active_label = "Your open PRs", "ready-for-review"
    print(f"{subject} — scope: {scope}")
    print(f"{total} open matching PRs; {len(active)} {active_label}, {len(drafts)} draft")
    if len(prs) < total:
        print(f"NOTE: showing {len(prs)} of {total} (GitHub search caps at {SEARCH_RESULT_CAP}).")
    print(
        f"Stale tiers: aging >={opts.warn_days}d, stale >={opts.stale_days}d, "
        f"abandoned >={opts.abandoned_days}d without activity."
    )

    shown = drafts if opts.drafts_only else active + (drafts if opts.include_drafts else [])

    for key, heading in (REVIEW_BUCKETS if opts.review_requested else AUTHOR_BUCKETS):
        group = sorted((p for p in shown if p["_bucket"] == key), key=sort_key)
        if not group:
            continue
        print(f"\n== {heading} ({len(group)}) ==")
        for pr in group:
            print(format_pr(pr))

    if opts.include_drafts or opts.drafts_only:
        group = sorted((p for p in shown if p["_bucket"] == "draft"), key=sort_key)
        if group:
            print(f"\n== Drafts ({len(group)}) ==")
            for pr in group:
                print(format_pr(pr))
    elif drafts:
        aged = sorted((p for p in drafts if p["_tier"]), key=sort_key)
        print(f"\n== Drafts ({len(drafts)}, not detailed) ==")
        if aged:
            print(f"  {len(aged)} past the {opts.warn_days}d mark:")
            for pr in aged:
                print(format_pr(pr))
        else:
            print(f"  All drafts had activity within {opts.warn_days} days.")
        print("  Re-run with --include-drafts for full detail.")

    if not shown:
        print("\nNothing matched. Try a wider scope, or --include-drafts.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pr_status.py",
        description="Triage open GitHub pull requests via the gh CLI.",
    )
    scope = parser.add_argument_group("scope")
    scope.add_argument("--org", help="limit to repos owned by this organization")
    scope.add_argument("--user", help="limit to repos owned by this user")
    scope.add_argument("--repo", metavar="OWNER/NAME", help="limit to a single repo")
    scope.add_argument(
        "--author", default="@me", help="PR author to search for (default: @me)"
    )
    scope.add_argument(
        "--review-requested",
        action="store_true",
        help="show PRs awaiting the author's review instead of their own PRs",
    )
    scope.add_argument(
        "--exclude-archived",
        action="store_true",
        help="drop PRs in archived repositories",
    )

    drafts = parser.add_mutually_exclusive_group()
    drafts.add_argument(
        "--include-drafts", action="store_true", help="show drafts in full detail"
    )
    drafts.add_argument(
        "--drafts-only", action="store_true", help="show only draft PRs"
    )

    tiers = parser.add_argument_group("staleness tiers (days without activity)")
    tiers.add_argument("--warn-days", type=int, default=7)
    tiers.add_argument("--stale-days", type=int, default=14)
    tiers.add_argument("--abandoned-days", type=int, default=30)

    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON instead of a report"
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    opts = parse_args(argv)
    if not shutil.which("gh"):
        die("the gh CLI is required but was not found on PATH")

    query = build_search_query(opts)
    now = datetime.now(timezone.utc)

    prs, total = fetch_pull_requests(query)
    annotate(prs, opts, now)
    fetch_failing_checks(prs)
    for pr in prs:
        pr["_bucket"] = classify(pr, opts.review_requested)

    if opts.as_json:
        payload = {
            "scope": query,
            "total": total,
            "fetched": len(prs),
            "generatedAt": now.isoformat(),
            "pullRequests": [
                {
                    "repository": pr["repository"]["nameWithOwner"],
                    "number": pr["number"],
                    "title": pr["title"],
                    "url": pr["url"],
                    "isDraft": pr["isDraft"],
                    "bucket": pr["_bucket"],
                    "staleTier": pr["_tier"],
                    "idleDays": pr["_idle_days"],
                    "daysSinceCommit": pr["_commit_days"],
                    "mergeable": pr["mergeable"],
                    "mergeStateStatus": pr["mergeStateStatus"],
                    "reviewDecision": pr["reviewDecision"],
                    "checksState": pr["_rollup"],
                    "failingChecks": pr["_failing_checks"],
                    "requestedReviewers": pr["_reviewers"],
                    "humanReviews": [
                        {"author": (r.get("author") or {}).get("login"), "state": r["state"]}
                        for r in pr["_human_reviews"]
                    ],
                    "botReviewCount": len(pr["_bot_reviews"]),
                    "additions": pr["additions"],
                    "deletions": pr["deletions"],
                    "changedFiles": pr["changedFiles"],
                    "notes": describe(pr),
                }
                for pr in sorted(prs, key=sort_key)
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    report(prs, total, opts, query)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
