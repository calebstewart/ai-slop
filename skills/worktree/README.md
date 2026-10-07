# worktree

One git worktree per piece of work, each with its own test environment, and a registry
that knows which Claude session is using which tree. Built for running several
independent PRs at once without two sessions sharing a checkout, a test database, or a
port, and for cleaning up afterwards without guessing.

The work is done by `bin/wt`, a standalone CLI (Python standard library, nothing to
install). The skill tells Claude how to drive it; an editor or a hook can drive it
directly.

## What it does

- **Names trees after the work.** `wt new sc-123456` finds the story's branch (or creates
  one from the story's type and title through the `short` CLI) and names the tree after
  it, without the `feature/` prefix. A story id is honoured strictly: several matching
  branches, or a story that cannot be looked up, is an error rather than a guess. Without
  a story, any existing branch or a plain description works too.
- **Gives each tree a slot.** A small integer, unique within the project. The repository's
  own `setup` hook turns it into resources — a test database suffix, a port offset, a
  Compose project — and hands back the environment variables to use. `wt exec -- <cmd>`
  runs a command in the tree with them. Optionally, idle slots stay *warm*, so the next
  tree reuses databases that already exist instead of rebuilding them.
- **Tracks sessions.** A tree is claimed by one session, and a session holds one tree.
  Another session cannot take a tree whose holder is still running; it can take one
  whose holder has ended, after confirming. A resumed session gets its own tree back
  without being asked.
- **Removes things carefully.** Removal is a dry run until confirmed. Uncommitted or
  unpushed work blocks it; so does a teardown hook that cannot tell what exists. A merged
  PR whose head is the tree's commit proves nothing can be lost, which is what makes
  squash-merged branches removable. `wt cleanup --stale` does this for every tree whose
  session has ended, skipping the ones that are not safe.
- **Notices drift.** `wt status` reports trees whose directory is gone, worktrees nobody
  registered, setups that were interrupted, and — with an `inventory` hook — resources no
  tree owns. Every finding comes with the command that fixes it.

## Using it

`/worktree on sc-123456`, `/worktree off`, `/worktree list`, `/worktree cleanup`. It is
also model-invoked, so "work on sc-123456 in a worktree" or "I'm done with this tree" is
usually enough.

Giving a repository its hooks:

```bash
~/.claude/skills/worktree/bin/wt init --local   # stubs in .claude/worktree/, kept out of git
```

Drop `--local` to commit the hooks for everyone instead. The hook contract — inputs,
outputs, dry runs, warm slots — is in [reference/hooks.md](reference/hooks.md).

## Install

Install the skill as usual (see the repository README), then check the CLI kept its
executable bit: `chmod +x ~/.claude/skills/worktree/bin/wt` if not.

`wt` does not need to be on your `PATH`. The skill runs it from its own directory, and
everything else should call it by full path. A symlink is a convenience for typing it
yourself; with one in place, `wt`'s suggested commands use the short name.

### Session-start reminder

Optional: a SessionStart hook that mentions trees left by ended sessions, and tells a
resumed session which tree it held. It prints nothing when there is nothing to say.

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "~/.claude/skills/worktree/bin/wt janitor --hook" }
        ]
      }
    ]
  }
}
```

## Driving it from an editor or a script

Every command takes `--json`, and nothing prompts; decisions come back as exit codes:

| Exit | Meaning |
|---|---|
| 0 | done; for `rm`/`cleanup` without `--yes`, a plan |
| 1 | error (`error`, `hint` in the JSON) |
| 2 | usage |
| 3 | held by another live session |
| 4 | held by an ended session; repeat with `--take-over` after asking |
| 5 | refused: unsafe, or a hook was not sure |

Inside a Claude session, `wt` identifies the session from `CLAUDE_CODE_SESSION_ID` and
`CLAUDE_PID`. Anything else that starts sessions — an editor plugin, say — passes
`--session <id> --pid <pid of the claude process>`. Liveness is that pid together with
its start time, so a reused pid never counts as the original session.

`wt env [name]` prints a tree's environment as `export` lines, for starting a process
(or a whole session) inside the tree with its environment already set.

## Where things are kept

- Registry: `~/.claude/wt/registry.sqlite` (SQLite, WAL), one database for every project,
  keyed by each repository's shared `.git` directory. `WT_HOME` moves it.
- Hook logs: `~/.claude/wt/logs/`.
- Trees: `<root>/.claude/worktrees/<name>`, which `wt` adds to `.git/info/exclude`.
- History: `wt log [name]`.

Needs `git` and `python3` 3.11+. `gh` adds PR state to removal plans; `short` resolves
stories that have no branch yet.
