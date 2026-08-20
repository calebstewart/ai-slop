# ai-slop

My personal pile of general-purpose AI slop.

This is a junk drawer, not a product. It holds whatever agent skills, prompts, and
scaffolding I've found useful enough to keep around and reuse across machines and
projects. Things here are written for my own workflows, get changed without warning,
and carry no promise of stability, backward compatibility, or good taste. Copy freely;
expectations, not so much.

Documentation for everything here is published at
**<https://calebstew.art/ai-slop/>**, generated from these same files.

## What's in here

Agent skills live under `skills/`, one directory per skill, each with a `SKILL.md`
following the [Agent Skills specification](https://agentskills.io/specification).
Each skill also has a `README.md` — that's the human-readable one; `SKILL.md` is
written for the agent.

| Skill | Description |
| --- | --- |
| [`artisanal-slop`](skills/artisanal-slop/README.md) | Mostly-automated GitHub issue resolution loop — classify, plan, implement, independently review, and merge open issues continuously. A bash state machine owns the decision tree; sub-agents do the work in a pool of persistent git worktrees. |
| [`pr-status`](skills/pr-status/README.md) | Triage of your open GitHub pull requests via the `gh` CLI — who has reviewed, what's failing, what conflicts, and what's gone stale — scoped to an org, a user, or the current repo. For start-of-day, start-of-week, or back-from-PTO catch-up. |
| [`writing-skills`](skills/writing-skills/README.md) | Guide for authoring high-quality Claude Code skills — writing `SKILL.md`, crafting the `description` field, choosing frontmatter, and structuring content with progressive disclosure. |

`artisanal-slop` ships an executable driver at `bin/artisanal-slop`. Whichever install
method you use, check the mode survived it — `chmod +x ~/.claude/skills/artisanal-slop/bin/artisanal-slop`
if it didn't.

## Installing skills

There is a fuller version of everything below — including a per-agent directory
table and a troubleshooting section — at
<https://calebstew.art/ai-slop/install/>.

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

## The site

<https://calebstew.art/ai-slop/> is a [Zola](https://www.getzola.org/) site built by
this repo's flake and deployed to GitHub Pages by `.github/workflows/pages.yml`. It is
themed to match [calebstew.art](https://calebstew.art), which links to it.

Nothing under `content/skills/` is committed. `scripts/generate-content.py` reads each
skill's `SKILL.md` frontmatter and `README.md` and writes the content tree at build time,
so a skill's prose lives in exactly one place and the site cannot drift from what you
actually install. The `metadata:` map in each `SKILL.md` carries the site-only fields
(tagline, tags, requirements); everything else on a skill's page is either its README
verbatim or derived from the filesystem.

The shape of the site is three levels, which is the same progressive disclosure
`writing-skills` argues for: a card catalog, then one page per skill, then its bundled
files. There is no persistent navigation — a skill page is a document, and the way back
up is the breadcrumb it renders itself.

`static/site.js` adds two things and neither is load-bearing: the catalog's search and
filter chips, and a copy button on install commands. Every card, command and link is in
the HTML, so with JavaScript off you get the whole catalog and no controls — the controls
are revealed by the script rather than hidden by it, so there is never a dead one.

Filter chips all read `facet: value` (`trigger: auto`, `tag: github`) and come from one
flat list the generator builds, so adding a facet is a change in one function. The chip's
facet name doubles as the card attribute it filters on — `tag` reads `data-tag` — and a
`nix flake check` guards that pairing, because when it drifts the chip renders perfectly
and silently matches nothing.

Two test scripts, neither wired into CI:

```bash
node tests/filter.test.js            # the filter, against the real site.js via a DOM stub
nix build .#site && python3 tests/link-check.py result
```

`filter.test.js` exists because the facet logic cannot otherwise be verified without a
browser; it is what caught the `data-tag`/`data-tags` mismatch. `link-check.py` resolves
every internal link the way a browser would from the page it appears on, against the
`/ai-slop/` prefix — the one class of bug that local preview cannot show you, since
`zola serve` runs at the root.

```bash
nix run            # regenerate content/, serve at http://127.0.0.1:1111, watch skills/
nix run .#gen      # regenerate content/ once and exit
nix flake check    # lint the skills; see below
nix build .#site   # the real build, output in ./result
```

`nix run` keeps watching `skills/` and regenerates when it changes, which Zola then picks
up and reloads — so editing a skill's README updates the browser. (Zola only watches
`content/`, which is generated, so without that you would be editing the source and
seeing nothing.)

Two things about `zola serve` that cost me an hour each, both worth knowing before they
cost you one: it writes into `public/`, so running `rm -rf public` while it is up will
quietly gut the served site while still answering requests for whatever it happens to
rebuild; and it does not recover from a build error in a file you subsequently fix, so a
mid-edit broken template leaves you with a 404 at the root until you restart it.

`nix develop` puts the same two commands on `PATH` as `slop-serve` and `slop-gen`, if you
would rather work in a shell.

`nix flake check` is as much a linter for the skills as a check on the site. It fails if a
`SKILL.md` `name` doesn't match its directory, if required `metadata:` fields are missing,
if a relative link in any README, `SKILL.md` or reference file doesn't resolve, if a
bundled script has a shebang but lost its executable bit, if a template or `site.js`
hardcodes a root-relative link (the site is served under the `/ai-slop/` path prefix, so
those break in production while looking fine locally), if `site.js` does not parse, or if
a filter chip's facet name has drifted from the card attribute it reads.

## License

[WTFPL](LICENSE) — do what the fuck you want to.
