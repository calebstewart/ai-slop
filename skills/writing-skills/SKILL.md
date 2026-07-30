---
name: writing-skills
description: Guide for authoring high-quality Claude Code skills — writing SKILL.md, crafting the description field, choosing frontmatter, and structuring content with progressive disclosure. Use when the user wants to create, write, author, scaffold, design, or improve a skill, a SKILL.md file, or a custom slash command.
---

# Writing Claude Code Skills

A skill is a directory containing a `SKILL.md` file. Claude loads it automatically when the request matches its `description`, or the user invokes it directly with `/<skill-name>`. Use this guide whenever creating or revising a skill.

This SKILL.md is the workflow and the rules you need every time. Load the reference files only when a step points you there:

- **[reference/best-practices.md](reference/best-practices.md)** — the authoring principles in depth: conciseness, descriptions, progressive disclosure, degrees of freedom, scripts, anti-patterns, the full pre-ship checklist.
- **[reference/frontmatter.md](reference/frontmatter.md)** — every frontmatter field, how the command name is derived, argument/string substitutions, and dynamic context injection.
- **[reference/templates.md](reference/templates.md)** — copy-paste starting points for the common skill shapes.
- **[reference/api-wrappers.md](reference/api-wrappers.md)** — how to wrap an API with no CLI: a bundled script exposing abstracted subcommands plus a generic passthrough, and how to describe that surface to Claude.

## Is a skill the right tool?

Create a skill when:
- You keep pasting the same instructions, checklist, or multi-step procedure into chat.
- A section of CLAUDE.md has grown into a *procedure* rather than a *fact*.
- You want reusable domain knowledge, conventions, or a workflow that loads on demand instead of sitting in context permanently.

Do **not** create a skill for a one-off task, a single fact (use CLAUDE.md or memory), or something Claude already does well unprompted. The default assumption is that Claude is already smart — only add what it does not already have.

## Workflow

Work through these steps in order. Each links to detail only when you need it.

### 1. Identify the gap (evaluation-first)

Before writing, run the task *without* a skill and watch where Claude struggles or where you repeatedly supply the same context. That gap — not an imagined requirement — is what the skill must close. Note 2-3 concrete scenarios you want it to handle; they are your test cases for step 7.

### 2. Choose the type and who invokes it

| Type | Content | Invocation |
|------|---------|------------|
| **Knowledge / reference** | Conventions, patterns, domain facts Claude applies to current work | Usually model-invoked; runs inline. |
| **Workflow / task** | Step-by-step actions (deploy, commit, generate) | Often user-only via `/name`; add `disable-model-invocation: true` so Claude never fires it on its own. |

Two independent toggles control invocation (see frontmatter reference for the table):
- `disable-model-invocation: true` → only the user can invoke it (use for anything with side effects — deploy, commit, send message).
- `user-invocable: false` → only Claude can invoke it (use for background knowledge that is not a meaningful user command).

If the skill should run in isolation with its own context, consider `context: fork` — but only for skills that contain an actual *task*, not pure guidelines.

### 3. Pick the location and name

| Location | Path | Scope |
|----------|------|-------|
| Personal | `~/.claude/skills/<name>/SKILL.md` | All your projects |
| Project | `.claude/skills/<name>/SKILL.md` | This repo (commit it to share) |
| Plugin | `<plugin>/skills/<name>/SKILL.md` | Where the plugin is enabled |

**The directory name becomes the command** (`~/.claude/skills/deploy-staging/` → `/deploy-staging`). The frontmatter `name` is only the display label — it does **not** change what the user types (except for a plugin-root SKILL.md). Keep the directory name and `name` in sync to avoid confusion.

Naming rules: lowercase letters, numbers, hyphens only; max 64 chars; no XML tags; **may not contain the reserved words "anthropic" or "claude"**. Prefer gerund form (`processing-pdfs`, `writing-documentation`) or a clear action (`deploy`, `fix-issue`). Avoid vague names (`helper`, `utils`, `tools`).

### 4. Write the frontmatter — the `description` is the highest-leverage line

Only `description` is recommended; everything else is optional. The description is loaded into the system prompt at startup and is how Claude (and the user) decide when to use the skill, so it must earn its place.

Rules for a good description:
- **Third person, always.** "Generates commit messages…" — never "I can help you…" or "You can use this to…". Mixed point-of-view hurts discovery.
- **State what it does AND when to use it**, with concrete trigger words a user would actually say. Put the key use case first (the listing is capped ~1,536 chars).
- **Be a little pushy about triggers.** Claude tends to *under*-trigger. Phrases like "Use when the user mentions X, Y, or Z" or "…even if they don't explicitly ask for a skill" widen activation.

```yaml
# Good
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDFs or when the user mentions forms or document extraction.
# Bad — vague, no triggers, wrong person
description: Helps with documents
description: I can process your PDFs for you
```

For the complete field list (`allowed-tools`, `argument-hint`, `arguments`, `model`, `effort`, `paths`, `context`, `agent`, `when_to_use`, …), see **[reference/frontmatter.md](reference/frontmatter.md)**.

### 5. Write the body — concise, imperative, structured

The body loads when the skill is invoked and then **stays in context for the rest of the session** (Claude does not re-read the file). Every line is a recurring token cost, so treat the context window as a public good.

- **Cut anything Claude already knows.** Don't explain what a PDF is or how libraries work. Challenge each sentence: "does this justify its tokens?"
- **Write as direct commands.** "Extract the palette. Read the template. Run the suite." Not "You should…" or "The skill will…". Number multi-step procedures.
- **Use consistent terminology** — pick one word per concept (always "field", never also "box"/"element") and one heading style.
- **Match specificity to fragility (degrees of freedom).** Open-ended task → give direction and trust Claude. Fragile/exact sequence → give the precise command and say "do not modify it." (Details and examples in best-practices.md.)
- **Prefer reasoned constraints over bare ALL-CAPS rules.** Briefly saying *why* a rule exists helps Claude handle edge cases; reserve strong "MUST/NEVER" for genuinely load-bearing rules.
- **No time-sensitive content** ("before August 2025…"). Put deprecated info in a collapsed "Old patterns" section instead.
- **No `@imports`** — they do not work in SKILL.md. Point to other files in prose: "See reference/foo.md for…".

### 6. Split detail into supporting files (progressive disclosure)

Keep `SKILL.md` under **500 lines**. When it grows past that — or covers multiple independent domains — move detail into sibling files that Claude reads only when needed.

- **Keep references one level deep.** Every supporting file links directly from SKILL.md. Avoid chains (SKILL → advanced.md → details.md); Claude may only partially read deeply-nested files.
- **Organize by domain** so an irrelevant domain costs zero tokens (`reference/finance.md`, `reference/sales.md`).
- **Give files descriptive names and a table of contents** if over ~100 lines, so partial reads still reveal the full scope.
- **Bundle scripts for deterministic work.** A pre-written `scripts/validate.py` is more reliable and cheaper than regenerated code; its source never enters context, only its output. Make execution intent explicit: "Run `scripts/x.py`" vs "See `scripts/x.py` for the algorithm." Use `${CLAUDE_SKILL_DIR}/scripts/...` so paths resolve at any install location. Use forward slashes always.
- **Wrapping an API with no CLI?** A common, well-defined case: bundle one script exposing abstracted subcommands for the frequent operations plus a generic `api` passthrough for the rest. See **[reference/api-wrappers.md](reference/api-wrappers.md)** for how to structure the script and describe its surface to Claude.

### 7. Test both paths and iterate

- Trigger it **automatically** by phrasing a request that matches the description; if it doesn't fire, the description needs the user's actual keywords (see Troubleshooting below).
- Trigger it **directly** with `/<name>`.
- Run your step-1 scenarios. Where the skill misses, sharpen the instruction or make the rule more prominent — iterate on observed behavior, not assumptions. The proven loop is: one Claude helps you *write* the skill; a fresh Claude *uses* it; you bring the gaps back. Live edits to `SKILL.md` under a watched directory take effect within the session.

## Troubleshooting

- **Doesn't trigger when expected** → description lacks the keywords the user naturally says; add them. Confirm it's listed via "What skills are available?".
- **Triggers too often** → make the description more specific, or add `disable-model-invocation: true`.
- **Stops influencing behavior mid-session** → the content is usually still present and the model drifted; strengthen the description/instructions, re-invoke after compaction, or enforce with a hook.

## Pre-ship checklist

- [ ] `description` is third-person, specific, and states what + when with real trigger words.
- [ ] Directory name is the intended command; `name` matches; lowercase/hyphens, no "anthropic"/"claude".
- [ ] Body is concise, imperative, consistent terminology, no content Claude already knows.
- [ ] SKILL.md under 500 lines; detail split into one-level-deep, descriptively-named files.
- [ ] No time-sensitive info, no `@imports`, no Windows-style paths.
- [ ] Invocation control (`disable-model-invocation` / `user-invocable`) matches intent; side-effecting workflows are user-only.
- [ ] Any bundled scripts handle their own errors and document their constants; execution-vs-read intent is explicit.
- [ ] Tested both invocation paths against the real scenarios from step 1.

The full annotated version of this checklist, with examples for each item, is in **[reference/best-practices.md](reference/best-practices.md)**.
