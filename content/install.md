+++
title = "Installing"
description = "Every way to get a skill from this repo into your agent, and how to keep it updated afterwards."
template = "page.html"
+++

A skill is just a directory with a `SKILL.md` in it. That means there is no installer to
trust and nothing to uninstall — the whole operation is "put this directory where your
agent looks for skills". Everything below is a different amount of ceremony around that
one idea.

If you only want the short version:

```bash
gh skill install calebstewart/ai-slop writing-skills --agent claude-code --scope user
```

## Where skills live

Worth knowing before you pick a method, because every method below is just a way of
writing to one of these directories.

| Agent | User scope (every project) | Project scope (one repo) |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Copilot, Cursor, Codex, Gemini CLI, others | varies | `.agents/skills/` |

`.agents/skills/` is a shared convention that several agents read, which is why
`gh skill` defaults to it. Check your own agent's docs, or run `gh skill install --help`
for the current list of supported hosts.

## Using `gh skill`

The [GitHub CLI](https://cli.github.com/) `skill` command — currently in preview —
handles discovery, placement, and update tracking. It is the method to prefer, because
it is the only one that leaves behind enough metadata to update the skill later.

```bash
gh skill install calebstewart/ai-slop writing-skills
```

That works, but it probably does not do what you want. Non-interactively `gh skill`
defaults to `--agent github-copilot --scope project`, so **be explicit**:

```bash
# Claude Code, available in every project
gh skill install calebstewart/ai-slop writing-skills --agent claude-code --scope user

# Claude Code, only inside the current repo
gh skill install calebstewart/ai-slop writing-skills --agent claude-code --scope project
```

### Reading one before you commit to it

```bash
gh skill preview calebstewart/ai-slop writing-skills
```

### Useful variations

```bash
# Faster: naming the exact path skips a full repo tree traversal
gh skill install calebstewart/ai-slop skills/writing-skills/SKILL.md --agent claude-code

# Pin to a tag or commit instead of the latest release / default branch HEAD
gh skill install calebstewart/ai-slop writing-skills@v1.2.3 --agent claude-code

# Drop it somewhere arbitrary, ignoring --agent/--scope
gh skill install calebstewart/ai-slop writing-skills --dir ~/some/other/place

# Overwrite an existing copy without being asked
gh skill install calebstewart/ai-slop writing-skills --agent claude-code --force
```

## Keeping it updated

`gh skill` injects source-tracking metadata into the installed `SKILL.md` frontmatter.
That is the whole reason updates work later:

```bash
gh skill update --dry-run          # report what's stale, change nothing
gh skill update --all              # update everything without prompting
gh skill update writing-skills     # just the one
```

`gh skill update --force` **overwrites local edits** to installed skill files with their
upstream content. If you have been tweaking an installed skill in place, keep your
version somewhere else — or use the symlink method below and stop fighting the tooling.

## Cloning and copying

No `gh` extension required. Slightly more typing, no update tracking.

```bash
git clone https://github.com/calebstewart/ai-slop.git
cd ai-slop
```

Then copy the skill directory to wherever your agent looks:

```bash
# User scope — available in every project
mkdir -p ~/.claude/skills
cp -R skills/writing-skills ~/.claude/skills/

# Project scope — only inside one repo
mkdir -p /path/to/your/project/.claude/skills
cp -R skills/writing-skills /path/to/your/project/.claude/skills/
```

## Symlinking, to track upstream

If you would rather follow changes than copy them:

```bash
ln -s "$PWD/skills/writing-skills" ~/.claude/skills/writing-skills
```

A `git pull` then updates the skill in place, and nothing can clobber local edits
because there are none — you are reading the repo directly. The trade is that symlinked
skills carry no `gh skill` source metadata, so `gh skill update` will not manage them.
You are choosing `git pull` as your update mechanism instead.

## The executable bit

`artisanal-slop` ships a driver at `bin/artisanal-slop`, and it has to stay executable.
Some copy, archive, and sync paths do not preserve the mode. Whichever method you used,
check that it survived:

```bash
test -x ~/.claude/skills/artisanal-slop/bin/artisanal-slop || \
  chmod +x ~/.claude/skills/artisanal-slop/bin/artisanal-slop
```

## Troubleshooting

**The skill does not appear in the `/` menu.** The command comes from the *directory*
name, not the `name` in frontmatter — so `~/.claude/skills/writing-skills/SKILL.md`
gives you `/writing-skills`. If you renamed the directory on the way in, that is your
command name. A skill with `user-invocable: false` is hidden from the menu by design.

**Claude never invokes it on its own.** Check for `disable-model-invocation: true` in
its frontmatter; `artisanal-slop` sets it deliberately, because something that opens and
merges pull requests should not start itself. Those skills are user-invoked only.

**It was invoked but seems not to have read its own reference files.** Skills use
progressive disclosure: the body loads on invocation, and linked reference files load
only when the agent decides it needs them. That is intended, not a failure.

**An installed skill stopped matching these pages.** These pages are generated from the
skill files in the default branch, so they describe `main`, not whatever tag you pinned.
Compare against the `SKILL.md` page for the skill, which is the same file your agent
reads.
