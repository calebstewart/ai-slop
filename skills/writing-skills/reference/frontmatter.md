# Frontmatter, Command Names & Substitutions (Claude Code)

Claude Code-specific reference. The two cross-surface required-ish fields are `name` and `description`; everything below is Claude Code's extension of the open Agent Skills standard.

## Contents
- Field reference
- How the command name is derived
- Invocation & context-loading matrix
- String substitutions
- Dynamic context injection
- Validation rules

## Field reference

All fields are optional; only `description` is recommended.

| Field | Purpose |
|-------|---------|
| `name` | Display label in skill listings. Defaults to the directory name. Does **not** set the typed command (except a plugin-root SKILL.md). |
| `description` | What the skill does and when to use it. Drives auto-invocation. If omitted, the first paragraph of the body is used. Combined with `when_to_use`, truncated ~1,536 chars in the listing — put the key use case first. |
| `when_to_use` | Extra trigger phrases / example requests, appended to `description` (counts toward the cap). |
| `argument-hint` | Autocomplete hint, e.g. `[issue-number]` or `[filename] [format]`. |
| `arguments` | Named positional args for `$name` substitution. Space-separated string or YAML list; names map to positions in order. |
| `disable-model-invocation` | `true` → only the user can invoke (via `/name`); Claude never auto-loads it, and it's not preloaded into subagents. Description leaves Claude's context. Default `false`. |
| `user-invocable` | `false` → hidden from the `/` menu; only Claude invokes it. For background knowledge that isn't a user action. Default `true`. |
| `allowed-tools` | Tools pre-approved (no permission prompt) while the skill is active. Does **not** restrict the pool. Space/comma string or YAML list. In a project `.claude/skills/`, takes effect after the workspace trust dialog. |
| `disallowed-tools` | Tools removed from the pool while active (e.g. block `AskUserQuestion` in an autonomous loop). Clears on the next user message. |
| `model` | Model for the rest of the current turn; resumes session model next prompt. Same values as `/model`, or `inherit`. |
| `effort` | Effort while active: `low`/`medium`/`high`/`xhigh`/`max` (availability depends on model). Default: inherit. |
| `context` | `fork` → run in a forked subagent context (no conversation history). Only meaningful for skills containing an actual task. |
| `agent` | With `context: fork`, which subagent type runs it (`Explore`, `Plan`, `general-purpose`, or a custom `.claude/agents/` type). Default `general-purpose`. Explore/Plan skip CLAUDE.md to stay lean. |
| `paths` | Glob patterns; when set, the skill auto-activates only when working on matching files. Comma string or YAML list. |
| `hooks` | Hooks scoped to this skill's lifecycle. |
| `shell` | `bash` (default) or `powershell` for `` !`cmd` `` blocks. PowerShell needs `CLAUDE_CODE_USE_POWERSHELL_TOOL=1`. |

## How the command name is derived

| Location | Command comes from |
|----------|--------------------|
| `~/.claude/skills/<dir>/` or `.claude/skills/<dir>/` | the **directory name** → `/<dir>` |
| Nested `.claude/skills/` clashing with another skill | path-qualified, e.g. `apps/web/.claude/skills/deploy/` → `/apps/web:deploy` |
| `.claude/commands/<file>.md` | file name → `/<file>` |
| Plugin `skills/<dir>/` | directory name, plugin-namespaced → `/<plugin>:<dir>` |
| Plugin **root** SKILL.md | frontmatter `name` (fallback: plugin dir) — the one case where `name` sets the command |

Precedence when names collide: enterprise > personal > project; a same-named skill at any level overrides a bundled skill; a skill beats a `.claude/commands/` file of the same name. Plugin skills are namespaced and can't collide.

## Invocation & context-loading matrix

| Frontmatter | User can invoke | Claude can invoke | Loading |
|-------------|:---:|:---:|---------|
| (default) | ✅ | ✅ | Description always in context; body loads on invoke |
| `disable-model-invocation: true` | ✅ | ❌ | Description **not** in context; body loads when user invokes |
| `user-invocable: false` | ❌ | ✅ | Description always in context; body loads on invoke |

**Lifecycle:** an invoked skill's rendered content enters the conversation once and persists for the session — Claude does not re-read it. Write standing instructions, not one-time steps. Auto-compaction re-attaches the most recent invocation of each skill (first ~5k tokens each, ~25k combined budget, newest first), so older skills may drop; re-invoke after compaction if needed.

You can also gate model access via permissions: `Skill(name)` exact, `Skill(name *)` prefix; deny `Skill` to disable all. The `skillOverrides` setting (`on`/`name-only`/`user-invocable-only`/`off`) controls visibility without editing the skill's own frontmatter.

## String substitutions

| Variable | Expands to |
|----------|-----------|
| `$ARGUMENTS` | All args as typed. If absent from the body, args are appended as `ARGUMENTS: <value>`. |
| `$ARGUMENTS[N]` / `$N` | Arg by 0-based index (`$0`, `$1`…). Shell-style quoting: `/skill "a b" c` → `$0`=`a b`, `$1`=`c`. |
| `$name` | Named arg declared in `arguments` frontmatter, mapped by position. |
| `${CLAUDE_SESSION_ID}` | Current session ID (logging, per-session files). |
| `${CLAUDE_EFFORT}` | `low`/`medium`/`high`/`xhigh`/`max` (ultracode reports `xhigh`). Adapt instructions to effort. |
| `${CLAUDE_SKILL_DIR}` | Directory holding this SKILL.md — use for bundled script paths regardless of CWD. |

Escape a literal `$` before a digit/`ARGUMENTS`/arg-name with a single backslash: `\$1.00`.

## Dynamic context injection

`` !`<command>` `` runs a shell command **before** the skill reaches Claude; its output replaces the placeholder. This is preprocessing — Claude sees only the result, never executes it.

```yaml
---
description: Summarize uncommitted changes. Use when the user asks what changed.
---
## Current changes
!`git diff HEAD`
## Instructions
Summarize the diff above in 2-3 bullets, then flag risks.
```

- Recognized only when `!` starts a line or follows whitespace (`KEY=!`cmd`` stays literal).
- Substitution runs once; injected output is not re-scanned for further placeholders.
- Multi-line: use a fenced ` ```! ` block.
- Disable globally with `"disableSkillShellExecution": true` (managed settings).

## Validation rules

- `name`: ≤64 chars, lowercase letters/numbers/hyphens only, no XML tags, **not** "anthropic"/"claude".
- `description`: non-empty, ≤1024 chars, no XML tags.
