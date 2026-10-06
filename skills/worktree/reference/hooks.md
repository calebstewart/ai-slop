# Repository hooks

How a repository tells `wt` to give each worktree its own environment. Read this when
setting a repository up (`wt init`) or debugging a hook.

- [Where they live](#where-they-live)
- [The slot](#the-slot)
- [setup](#setup)
- [teardown](#teardown)
- [inventory](#inventory)
- [Settings](#settings)
- [Writing good hooks](#writing-good-hooks)

## Where they live

`<root>/.claude/worktree/`, in the **root checkout**. Hooks always run from there, never
from a tree's own copy, so they work whether the directory is committed or ignored, and
teardown still works for a tree whose directory is gone. Every hook is optional; a
repository without any still gets trees, names, slots and claims.

`wt init` writes commented stubs. `wt init --local` also adds the directory to
`.git/info/exclude`, so it stays personal without touching `.gitignore`.

A hook must be executable; `wt` reports a non-executable hook as an error rather than
skipping it.

## The slot

Every tree holds a small integer, `WT_SLOT`, unique among the project's trees. It is the
only isolation `wt` provides: hooks turn it into real resources.

| Resource | From the slot |
|---|---|
| Test databases | a suffix: `TEST_ENV_NUMBER=$WT_SLOT` |
| Ports | an offset: `$((10000 + WT_SLOT * 100))` |
| Docker Compose | a project: `COMPOSE_PROJECT_NAME=$WT_PROJECT-wt$WT_SLOT` |
| Redis | a database index |

`slot_min` reserves low numbers — for example when the root checkout already uses test
environment 1, start at 2.

**Warm slots.** With `warm_slots = N`, up to N idle slots keep their resources after their
tree is removed (`WT_TEARDOWN_MODE=release`), and a new tree prefers one of them
(`WT_SLOT_WARM=1`) — so setup can skip building databases that already exist. Beyond N,
teardown is asked to `destroy`.

## setup

Runs after `wt new` or `wt adopt` creates or registers a tree, and again on `wt setup`.
cwd is the tree.

| Variable | Value |
|---|---|
| `WT_NAME`, `WT_BRANCH`, `WT_PATH` | the tree |
| `WT_ROOT`, `WT_PROJECT`, `WT_GIT_COMMON_DIR` | the root checkout, its directory name, the shared `.git` |
| `WT_SLOT` | the slot |
| `WT_SLOT_WARM` | `1` if the slot's resources survived from an earlier tree |
| `WT_ENV_OUT` | a file to append `KEY=VALUE` lines to |

Lines in `WT_ENV_OUT` are stored in the registry and become the environment of every
`wt exec` in the tree, and of its teardown. Values are taken literally (no quoting or
expansion); `export ` prefixes and `#` comments are allowed; `WT_*` names are reserved.

Exit non-zero and the tree is kept but marked `broken`, with the log path in its error.
Output goes to a log under `~/.claude/wt/logs/`; `-v` streams it as well.

## teardown

Runs twice per removal: first with `WT_DRY_RUN=1` while `wt` builds the plan, then with
`WT_DRY_RUN=0` when the user applies it. cwd is the tree, or the root checkout when the
tree's directory is gone. It sees everything setup saw, everything setup wrote, and:

| Variable | Value |
|---|---|
| `WT_TEARDOWN_MODE` | `release` (keep resources, the slot stays warm) or `destroy` |
| `WT_DRY_RUN` | `1`: print what you would do and change nothing |

**Exiting non-zero means "not sure"**, and nothing is removed: the dry run blocks the
plan; a failed real run leaves the tree `broken` so `wt rm` can be retried. Use that
whenever the hook cannot see what exists — a database server that is down, a failed
authentication query — rather than reporting "nothing to clean".

`wt slots purge N` also calls teardown, in `destroy` mode, for a slot no tree owns; then
`WT_NAME`, `WT_BRANCH` and `WT_PATH` are empty and nothing from setup is available.

## inventory

Optional. Prints the slot numbers that have resources in reality, one per line. `wt
status` compares that with the registry:

- **LEAKED**: resources for a slot no tree or warm slot accounts for. If a tree still
  uses them, `wt adopt <path> --slot N --warm`; to keep them for reuse, `wt slots warm N`;
  to destroy them, `wt slots purge N`.
- **COLD**: a slot recorded as warm that has no resources.
- **UNKNOWN**: the hook failed or printed something that is not a number. Never treated
  as "nothing leaked".

## Settings

`config.toml`. All optional; unknown keys and wrong types are errors.

| Key | Default | Meaning |
|---|---|---|
| `slot_min`, `slot_max` | `1`, `999` | the slot range |
| `warm_slots` | `0` | idle slots that keep their resources |
| `worktrees_dir` | `".claude/worktrees"` | where new trees go, relative to the root |
| `remote` | `"origin"` | |
| `base` | `""` | start point for new branches; empty means `<remote>/HEAD` |
| `fetch` | `true` | fetch the base before branching from it |
| `branch_types` | `feature`, `bug`, `chore`, … | leading branch segments dropped from tree names |
| `default_type` | `"feature"` | prefix for branches made from a description |
| `story_branch` | `"{type}/sc-{id}-{slug}"` | branch for a story that has none |
| `slug_max`, `name_max` | `50`, `60` | length caps |
| `unmanaged` | `["agent-*"]` | trees under `worktrees_dir` that `wt` ignores |

## Writing good hooks

- **Idempotent.** Setup can rerun on a half-built tree; teardown can rerun after a failure.
  Use "create if missing" and "drop if exists".
- **Honest dry runs.** The dry run is what the user approves; print exactly what the real
  run would touch.
- **Refuse rather than guess.** When the state cannot be read, exit non-zero.
- **Fast on warm slots.** Check `WT_SLOT_WARM` and skip what already exists; leave schema
  drift to the application's own migration checks.
- **POSIX sh or any executable.** The stubs are `#!/bin/sh`; anything with a shebang works.
