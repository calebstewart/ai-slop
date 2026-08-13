# ai-slop

My personal pile of general-purpose AI slop.

This is a junk drawer, not a product. It holds whatever agent skills, prompts, and
scaffolding I've found useful enough to keep around and reuse across machines and
projects. Things here are written for my own workflows, get changed without warning,
and carry no promise of stability, backward compatibility, or good taste. Copy freely;
expectations, not so much.

## What's in here

Agent skills live under `skills/`, one directory per skill, each with a `SKILL.md`
following the [Agent Skills specification](https://agentskills.io/specification).
Each skill also has a `README.md` — that's the human-readable one; `SKILL.md` is
written for the agent.

| Skill | Description |
| --- | --- |
| [`artisanal-slop`](skills/artisanal-slop/README.md) | Mostly-automated GitHub issue resolution loop — classify, plan, implement, independently review, and merge open issues continuously. A bash state machine owns the decision tree; sub-agents do the work in a pool of persistent git worktrees. |
| [`writing-skills`](skills/writing-skills/README.md) | Guide for authoring high-quality Claude Code skills — writing `SKILL.md`, crafting the `description` field, choosing frontmatter, and structuring content with progressive disclosure. |

`artisanal-slop` ships an executable driver at `bin/artisanal-slop`. Whichever install
method you use, check the mode survived it — `chmod +x ~/.claude/skills/artisanal-slop/bin/artisanal-slop`
if it didn't.

## Installing skills

### Primary: `gh skill`

The [GitHub CLI](https://cli.github.com/) `skill` command (currently in preview)
handles discovery, placement, and update tracking. Install a skill by naming this
repo and the skill:

```bash
gh skill install calebstewart/ai-slop writing-skills
```

Placement is controlled by `--agent` and `--scope`. Non-interactively, `gh skill`
defaults to `--agent github-copilot --scope project`, so be explicit if you want
something else. For Claude Code, installed everywhere:

```bash
gh skill install calebstewart/ai-slop writing-skills --agent claude-code --scope user
```

Useful variations:

```bash
# Read a skill before committing to it
gh skill preview calebstewart/ai-slop writing-skills

# Faster install — exact path skips a full repo tree traversal
gh skill install calebstewart/ai-slop skills/writing-skills/SKILL.md --agent claude-code

# Project scope (into the current git repo) instead of user scope
gh skill install calebstewart/ai-slop writing-skills --agent claude-code --scope project

# Pin to a tag or commit instead of latest release / default branch HEAD
gh skill install calebstewart/ai-slop writing-skills@v1.2.3 --agent claude-code

# Drop it somewhere arbitrary, ignoring --agent/--scope
gh skill install calebstewart/ai-slop writing-skills --dir ~/some/other/place

# Overwrite an existing copy without being asked
gh skill install calebstewart/ai-slop writing-skills --agent claude-code --force
```

`gh skill` injects source-tracking metadata into the installed `SKILL.md`
frontmatter, which is what makes updates work later:

```bash
gh skill update --dry-run          # report what's stale, change nothing
gh skill update --all              # update everything without prompting
gh skill update writing-skills     # just the one
```

Note that `gh skill update --force` overwrites local edits to installed skill files
with their upstream content, so keep your own modifications somewhere else.

### Alternative: clone and copy

No `gh` extension required — a skill is just a directory, so copying it into your
agent's skills directory is enough.

```bash
git clone https://github.com/calebstewart/ai-slop.git
cd ai-slop
```

Then copy the skill directory to wherever your agent looks for skills. For Claude
Code:

```bash
# User scope — available in every project
mkdir -p ~/.claude/skills
cp -R skills/writing-skills ~/.claude/skills/

# Project scope — only inside one repo
mkdir -p /path/to/your/project/.claude/skills
cp -R skills/writing-skills /path/to/your/project/.claude/skills/
```

Other agents use different directories — `.agents/skills/` is shared by several
(Copilot, Cursor, Codex, Gemini CLI, and others) at project scope. Check your
agent's docs, or run `gh skill install --help` for the current list of supported
hosts.

If you'd rather track upstream changes without copying, symlink instead:

```bash
ln -s "$PWD/skills/writing-skills" ~/.claude/skills/writing-skills
```

A `git pull` then updates the skill in place. Symlinked skills have no `gh skill`
source metadata, so `gh skill update` won't manage them — that's the trade.

## License

[WTFPL](LICENSE) — do what the fuck you want to.
