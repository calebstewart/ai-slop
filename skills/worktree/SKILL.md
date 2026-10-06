---
name: worktree
description: Works on a story, branch, or task in its own git worktree with an isolated test environment, tracked per project and per Claude session, and tears it down cleanly afterwards. Use when the user wants to start or switch work ("work on sc-123456", "start a worktree for this", "pick up that branch"), finish or remove a tree ("I'm done with this", "clean up the worktree"), see which trees exist or which session holds them, clean up trees left by ended sessions, or set up a repository's worktree hooks. Also use when a session-start message mentions wt.
argument-hint: "[on <story|branch|description> | off [name] | list | cleanup | init]"
allowed-tools: Bash, AskUserQuestion, Read
license: WTFPL-2.0
metadata:
  tagline: "Isolated git worktrees per PR — named from the story, set up and torn down by the repo's own hooks, claimed by one session at a time."
  tags: "git, worktrees, workflow, shortcut"
  requires: "git, python3 3.11+; optionally gh, short"
---

# Working in isolated worktrees

`${CLAUDE_SKILL_DIR}/bin/wt` owns all worktree state: the registry, slots, session
claims, and running the repository's setup and teardown hooks. Run it for every
worktree operation. Do not run `git worktree add/remove`, edit its database, or
call the repo's hooks yourself — the registry would stop matching reality.

Always pass `--json` when you will act on the result. Run it as the full path above,
from anywhere in the repository or with `-C <dir>`; its suggested fixes (`hint`, `fix`)
are spelled the same way, so they can be run as printed. `notes` in its output are
context — mention one to the user only if it changes a decision.

| Exit | Meaning | Do |
|---|---|---|
| 0 | done; for `rm`/`cleanup` without `--yes`, a plan that is safe to apply | continue |
| 1 | error | show `error` and `hint` |
| 2 | usage error | fix the command line |
| 3 | held by another session that is still running | stop; say which session (`holder`) |
| 4 | held by a session that has ended | ask the user, then repeat with `--take-over` |
| 5 | refused, or a dry run that is blocked: unsafe, or a hook was not sure | read `plan.blocked`; never force it on your own |

Subagents share this session's identity, so they share its claim: a subagent works in
this session's tree or not in a tree at all.

## Pick the action

From the argument or the request: **on** (start or resume work), **off** (finish a
tree), **list** / **status**, **cleanup**, or **init** (give a repo its hooks — read
[reference/hooks.md](reference/hooks.md) first). No argument: run `list` and ask.

## on — start or resume work

1. Pass what the user gave you, unchanged and quoted as one argument:
   `wt new "<input>" --json`. A story id (`sc-123456` or the bare number), an existing
   branch, or a description all work.
   If they gave only a description and have not said there is no story, ask once
   whether there is one — a story id makes the branch and tree name follow it.
2. If `new` says the tree is already registered or the branch is checked out in a
   registered tree, run `wt claim <name> --json` instead.
3. On exit 4, ask with `AskUserQuestion`: the tree was last used by session
   `holder.session`, which has ended — take it over? On yes, rerun with `--take-over`.
   On exit 3, do not retry: report who holds it.
4. If setup failed (exit 1 with a `log`), the tree exists but is `broken`. Show the
   relevant part of the log, help fix the cause, then `wt setup <name> --json`.

Then tell the user the tree name, branch, slot, and path, and work **only** in it:

- Edit files by absolute path under the tree's `path`. Never edit the root checkout
  for this work.
- Run every command through `wt exec -- <command>`. It runs in the tree — relative
  paths like `./bin/test` resolve there — with the environment setup produced (test
  database numbers, ports, …), which plain Bash calls do not have. With no name it
  uses this session's tree. Its output is the command's own; `--json` does not apply.
- Plain git needs no environment: `git -C <path> …` is fine.

A session holds one tree; claiming another releases the first (the tree stays).

## off — finish a tree

1. `wt rm <name> --json` (no `--yes`) prints a plan and changes nothing. With no name
   given, use this session's tree (`wt list --json`, `holder.mine`).
2. If `plan.blocked` is non-empty, resolve each reason with the user — never reach for
   `--force` yourself:
   - **uncommitted changes**: summarize them (`git -C <path> status --short`, `diff
     --stat`) and ask: commit and push, discard (then `--force`), or keep the tree.
   - **unpushed commits**: offer to push (`git -C <path> push -u <remote> <branch>`,
     using the remote the reason names). Then run the dry run again.
   - **teardown is not sure**: show `plan.teardown.output`. Usually a service is down;
     fix that and retry. `--skip-teardown` leaves resources behind — only on request.
3. Branch: `plan.branch_action` is `-D` when a merged PR's head is the tree's commit,
   so nothing can be lost; `null` means the branch is kept. Pass `--delete-branch` only
   if the user asks.
4. If your Bash working directory is inside the tree, `cd` to the root first (or use
   `-C <root>` throughout). Then `wt rm <name> --yes --json` and report `result`: the
   teardown it ran (`result.teardown`) and what happened to the branch.

## list, status

`wt list --json` shows the project's trees, their state, and who holds each (`holder`:
`live`, `ended`, or `none`; `mine` marks this session; `label` is the holding session's
name when it is running). `wt status --json` reports problems, each with a `fix` —
summarize them and offer the fixes; run destructive ones (`rm`, `slots purge`) only
after the user agrees.

"What is there, is anything left to clean up?" is `list`, `status`, and the dry run of
`cleanup --stale`.

## cleanup — trees whose session has ended

1. `wt cleanup --stale --json` is a dry run. Summarize: which trees would go, and which
   are skipped and why (uncommitted or unpushed work, a live holder, unsure teardown).
2. Confirm once with `AskUserQuestion`, then rerun with `--yes`. Skipped trees need the
   `off` treatment one by one.
3. Trees nobody has claimed are left alone unless the user asks to include them
   (`--include-unclaimed`).

## At session start

A SessionStart hook may run `wt janitor --hook`. If it says this session holds a tree,
the session was resumed: run `wt claim <name> --json` (no prompt is needed for your own
tree) and keep working there. Mention any other janitor lines to the user once.
