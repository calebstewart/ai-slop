# writing-skills

A guide for writing agent skills, written as an agent skill. It loads when you ask
Claude to create, author, scaffold, or improve a skill or a custom slash command, and
turns "write me a skill for X" from an improvisation into a repeatable procedure.

Mildly recursive, and the one thing in this repo that makes the rest of it easier to
produce.

## What it covers

The `SKILL.md` body is the part needed every time — a seven-step workflow, plus
troubleshooting and a pre-ship checklist:

1. **Identify the gap first.** Run the task without a skill and watch where Claude
   struggles. That gap is the skill; an imagined requirement isn't.
2. **Choose the type** — passive knowledge Claude applies on its own, versus a workflow
   the user fires deliberately — and set the invocation toggles to match.
3. **Pick the location and name**, including the rule people trip on most: the
   *directory* name is what becomes the `/command`, not the frontmatter `name`.
4. **Write the `description`.** The highest-leverage line in the file, since it's the
   only part always resident in context and the sole basis for auto-invocation.
5. **Write the body** — concise, imperative, consistent terminology, nothing Claude
   already knows. It stays in context for the whole session, so every line is a
   recurring cost.
6. **Split detail into supporting files** so irrelevant sections cost nothing.
7. **Test both invocation paths** against the scenarios from step 1 and iterate on
   observed behavior.

## Reference material

Detail lives in sibling files that get read only when a step points at them:

| File | Contents |
| --- | --- |
| [`reference/best-practices.md`](reference/best-practices.md) | The authoring principles in depth — conciseness, descriptions, progressive disclosure, degrees of freedom, bundled scripts, anti-patterns, and the annotated pre-ship checklist. |
| [`reference/frontmatter.md`](reference/frontmatter.md) | Every frontmatter field, how the command name is derived, the invocation matrix, string substitutions, and dynamic context injection. |
| [`reference/templates.md`](reference/templates.md) | Copy-paste starting points for the common skill shapes. |
| [`reference/api-wrappers.md`](reference/api-wrappers.md) | Wrapping an API that has no CLI: one bundled script with abstracted subcommands plus a generic passthrough, and how to describe that surface. |

## Using it

Model-invoked, so usually you don't invoke it at all — asking for a new skill is
enough. `/writing-skills` works if it doesn't fire on its own.

Most of the guidance is Claude Code-specific (frontmatter fields, `/command`
derivation, invocation control), but the workflow and authoring principles carry over
to any agent that reads a `SKILL.md`.

## The opinion underneath it

Two ideas do most of the work here, and both push toward writing *less*:

- **Claude is already smart.** A skill should contain only what the model lacks —
  your conventions, your fragile sequences, your domain facts. Explaining things it
  already knows is pure token cost.
- **The context window is a public good.** Your skill shares it with the system
  prompt, the conversation, every other skill's metadata, and the user's actual
  question. Detail belongs in files that load on demand, not in the body.
