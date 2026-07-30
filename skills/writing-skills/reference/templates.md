# Starter Templates

Copy the shape that matches your skill, then strip the comments. Replace the directory name to set the command (`~/.claude/skills/<name>/SKILL.md` → `/<name>`).

## 1. Knowledge / reference skill (model-invoked, inline)

For conventions or domain knowledge Claude should apply automatically. No task — just guidance.

```markdown
---
name: api-conventions
description: REST API design conventions for this codebase. Use when writing, reviewing, or modifying API endpoints, controllers, or route handlers.
---

# API Conventions

When writing API endpoints:
- Use RESTful resource naming; plural nouns for collections.
- Return the standard error envelope: `{ "error": { "code", "message" } }`.
- Validate request bodies before touching the database.

For the full error-code catalog, see [reference/errors.md](reference/errors.md).
```

## 2. Workflow / command skill (user-invoked, side effects)

For actions you trigger deliberately. `disable-model-invocation` keeps Claude from firing it on its own; `allowed-tools` pre-approves the exact commands it runs.

```markdown
---
name: deploy
description: Deploy the application to production.
disable-model-invocation: true
allowed-tools: Bash(npm test*) Bash(npm run build*) Bash(git push*)
argument-hint: [environment]
---

Deploy to $ARGUMENTS (default: production):

1. Run the test suite. Stop and report if anything fails.
2. Build the application.
3. Push to the deployment target.
4. Verify the deployment responds, then report the URL.
```

## 3. Skill with dynamic context injection

Pull live data into the prompt before Claude reads it.

```markdown
---
name: summarize-changes
description: Summarize uncommitted changes and flag risks. Use when the user asks what changed, wants a commit message, or asks to review their diff.
---

## Current changes
!`git diff HEAD`

## Instructions
Summarize the diff above in two or three bullets, then list risks
(missing error handling, hardcoded values, tests needing updates).
If the diff is empty, say there are no uncommitted changes.
```

## 4. Forked-task skill with a bundled script

Runs in an isolated context; the body is the task. `${CLAUDE_SKILL_DIR}` resolves the script path at any install location.

```markdown
---
name: codebase-visualizer
description: Generate an interactive tree visualization of the codebase. Use when exploring a new repo or understanding project structure.
allowed-tools: Bash(python3 *)
---

# Codebase Visualizer

Run from the project root:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/visualize.py .
```

This writes `codebase-map.html` and opens it in the browser.
```

Directory layout for #4:
```
codebase-visualizer/
├── SKILL.md
└── scripts/
    └── visualize.py     # executed, never loaded into context
```

## 5. API-wrapper skill (no CLI available)

Bundles one script exposing named subcommands plus a generic passthrough. Full guidance and an annotated script in [api-wrappers.md](api-wrappers.md).

```markdown
---
name: example-api
description: Interact with the Example REST API — read and create issues. Use when the user asks to look up, list, or create Example issues, or to call the Example API.
allowed-tools: Bash(*api.sh *)
---

# Example API

Interact via `${CLAUDE_SKILL_DIR}/scripts/api.sh`. Requires `EXAMPLE_API_TOKEN` in the environment.

- `api.sh get-issue <n>` — fetch one issue (JSON)
- `api.sh list-issues [state]` — list issues, default `open`
- `api.sh create-issue <title> [body]` — create an issue
- `api.sh api <METHOD> <path> [json]` — any other endpoint (escape hatch)

Use a named subcommand when one exists; fall back to `api` otherwise. Run `api.sh help` to see the surface.
```

Directory layout:
```
example-api/
├── SKILL.md
└── scripts/
    └── api.sh        # dispatch + generic passthrough; executed, never loaded
```

## 6. Progressive-disclosure skill (multi-domain reference)

SKILL.md is pure navigation; each domain file loads only when relevant.

```markdown
---
name: bigquery-analysis
description: Query and analyze the company data warehouse. Use when the user asks about revenue, pipeline, product usage, or marketing metrics in BigQuery.
---

# BigQuery Analysis

Always exclude test accounts (`is_test = false`) from every query.

## Datasets
- **Finance** — revenue, ARR, billing → [reference/finance.md](reference/finance.md)
- **Sales** — pipeline, accounts → [reference/sales.md](reference/sales.md)
- **Product** — API usage, adoption → [reference/product.md](reference/product.md)

Find a metric fast: `grep -i "<metric>" reference/*.md`
```
