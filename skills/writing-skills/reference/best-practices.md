# Skill Authoring — Best Practices in Depth

Detail behind the SKILL.md workflow. Read the section you need.

## Contents
- Conciseness: the context window is a public good
- Writing effective descriptions
- Degrees of freedom: match specificity to fragility
- Progressive disclosure patterns
- Workflows, checklists, and feedback loops
- Scripts and executable code
- Content guidelines (terminology, time-sensitivity, templates, examples)
- Anti-patterns
- Evaluation and iteration (Claude A / Claude B)
- Annotated pre-ship checklist

## Conciseness: the context window is a public good

Your skill shares context with the system prompt, conversation history, other skills' metadata, and the user's actual request. Only `name`/`description` are pre-loaded; the body loads on invocation — but once loaded it **stays for the session**, so every line is a recurring cost.

Default assumption: **Claude is already very smart.** Add only what it lacks. Challenge each piece: "Does Claude need this? Can I assume it knows? Does this paragraph justify its tokens?"

**Concise (~50 tokens):**
````markdown
## Extract PDF text
Use pdfplumber:
```python
import pdfplumber
with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```
````

**Too verbose (~150 tokens):** a paragraph explaining what PDFs are, that libraries exist, that pdfplumber is one option, how to pip install it… all of which Claude already knows.

## Writing effective descriptions

The description is the single most important field — Claude picks among potentially 100+ skills using it alone.

- **Third person, always.** "Processes Excel files and generates reports." Never "I can help…" / "You can use this…". Inconsistent point-of-view causes discovery problems.
- **What + when.** Include the capability and the specific triggers/contexts. Front-load the key use case (listing capped ~1,536 chars; overflow drops least-used skills' descriptions first).
- **Concrete trigger terms.** Use words the user actually says ("spreadsheet", ".xlsx", "commit message", "diff"). Claude under-triggers, so being a bit pushy ("Use when…", "even if they don't explicitly ask") helps.

Good:
```yaml
description: Analyze Excel spreadsheets, create pivot tables, generate charts. Use when analyzing Excel files, spreadsheets, tabular data, or .xlsx files.
description: Generate descriptive commit messages by analyzing git diffs. Use when the user asks for help writing commit messages or reviewing staged changes.
```
Bad: `Helps with documents` · `Processes data` · `Does stuff with files`

## Degrees of freedom: match specificity to fragility

Think of Claude as a robot on a path.

- **Open field (high freedom)** — many valid approaches; decisions depend on context. Give direction, trust Claude. *Example: a code-review process described as 4 general steps.*
- **Preferred pattern (medium freedom)** — a template or parameterized script with acceptable variation.
- **Narrow bridge with cliffs (low freedom)** — fragile, must run in exact sequence. Give the precise command and forbid changes: "Run exactly `python scripts/migrate.py --verify --backup`. Do not modify the command or add flags."

Over-constraining an open task wastes tokens and judgment; under-constraining a fragile one causes errors.

## Progressive disclosure patterns

SKILL.md is a table of contents that points to detail loaded on demand.

**Pattern 1 — High-level guide with references.** Quick-start inline; "For form filling, see FORMS.md; for the API, see REFERENCE.md."

**Pattern 2 — Domain organization.** Split by domain so unrelated domains cost nothing:
```
bigquery-skill/
├── SKILL.md            # overview + navigation
└── reference/
    ├── finance.md
    ├── sales.md
    └── product.md
```
A `grep -i "revenue" reference/finance.md` hint helps Claude jump straight to the right place.

**Pattern 3 — Conditional detail.** Show the common path inline; link advanced/edge cases ("For tracked changes, see REDLINING.md").

**Keep references one level deep.** SKILL.md → file.md is fine; SKILL.md → a.md → b.md is not — Claude may `head` deeply-nested files and read them incompletely. **Add a table of contents** to any reference file over ~100 lines so partial reads still reveal full scope.

## Workflows, checklists, and feedback loops

For complex multi-step work, give an explicit checklist Claude can copy into its response and tick off:
```
Task Progress:
- [ ] Step 1: Analyze the form (run analyze_form.py)
- [ ] Step 2: Create field mapping (edit fields.json)
- [ ] Step 3: Validate (run validate_fields.py)
- [ ] Step 4: Fill (run fill_form.py)
- [ ] Step 5: Verify (run verify_output.py)
```
Clear numbered steps stop Claude skipping validation.

**Feedback loop:** run validator → fix → repeat, and "only proceed when validation passes." Works with scripts (`validate.py`) or with a reference doc as the "validator" (compare against STYLE_GUIDE.md). For batch/destructive/high-stakes work, use **plan → validate → execute**: have Claude write a structured plan file, validate it with a script (verbose, specific errors), then apply.

## Scripts and executable code

Pre-written scripts beat regenerated code: more reliable, no code in context, consistent, faster.

- **Solve, don't punt.** Handle `FileNotFoundError`/`PermissionError` etc. inside the script rather than letting it throw for Claude to untangle.
- **No voodoo constants.** Justify values in a comment (`REQUEST_TIMEOUT = 30  # slow connections`), not `TIMEOUT = 47`.
- **State execution intent.** "Run `analyze_form.py` to extract fields" (execute) vs "See `analyze_form.py` for the algorithm" (read).
- **Forward slashes only** (`scripts/helper.py`), never backslashes — Unix paths work everywhere.
- **Don't assume packages exist.** List required packages and install instructions; remember the API surface has no network/runtime install (Claude Code has full network access, but installing globally is discouraged — install locally).
- **MCP tools need fully-qualified names:** `ServerName:tool_name` (e.g. `GitHub:create_issue`), else "tool not found".
- **Reference `${CLAUDE_SKILL_DIR}`** for bundled script paths so they resolve at personal/project/plugin install locations.

For the specific case of wrapping an API with no CLI (a bundled script with abstracted subcommands plus a generic passthrough), see [api-wrappers.md](api-wrappers.md).

## Content guidelines

- **Consistent terminology.** One term per concept throughout ("API endpoint", not also "URL"/"route"/"path").
- **No time-sensitive info.** Replace "after August 2025 use v2" with a "Current method" section plus a collapsed `<details>` "Old patterns (deprecated)" block.
- **Templates** for output format — strict ("ALWAYS use this exact template") or flexible ("a sensible default, adapt as needed"), matching how rigid the format must be.
- **Examples** — for style-sensitive output, give input/output pairs, just like few-shot prompting. Concrete beats abstract.

## Anti-patterns

- **Vague descriptions** with no triggers.
- **Verbose bodies** re-explaining what Claude knows.
- **Too many options.** Give one default with an escape hatch ("Use pdfplumber. For scanned PDFs needing OCR, use pdf2image + pytesseract") — not "you could use pypdf, or pdfplumber, or PyMuPDF, or…".
- **Deeply nested references** (more than one level from SKILL.md).
- **`@imports` in SKILL.md** — they don't work; link in prose.
- **Windows-style paths.**
- **Cross-skill dependencies** — they break modularity; keep skills self-contained.
- **Rules overfit to one test case** — they don't generalize. Name the underlying anti-pattern instead.
- **Bare ALL-CAPS rule walls** — explain *why* a constraint exists; reserve strong MUST/NEVER for load-bearing rules and repeat the few that truly matter.

## Evaluation and iteration (Claude A / Claude B)

Build evaluations **before** extensive docs, so you solve real gaps:
1. Run representative tasks with no skill; record failures.
2. Write ~3 concrete test scenarios with expected behaviors.
3. Measure the baseline.
4. Write the minimum instructions to pass them.
5. Iterate against the baseline.

Develop with two roles: **Claude A** helps you write/refine the skill; a fresh **Claude B** uses it on real tasks; you observe B's behavior and bring specifics back to A ("B forgot to filter test accounts even though the skill mentions it — make that rule more prominent"). Watch for: unexpected file-read order (structure unclear), missed references (links not prominent), a file never read (unnecessary or poorly signaled), repeated reads of one file (maybe promote it into SKILL.md). Iterate on observed behavior, not assumptions.

## Annotated pre-ship checklist

**Core quality**
- [ ] Description specific, includes key terms, states what + when, third person.
- [ ] SKILL.md body under 500 lines; detail in separate files.
- [ ] References one level deep; files named descriptively; TOC if >100 lines.
- [ ] No time-sensitive info (or quarantined in "Old patterns").
- [ ] Consistent terminology; examples concrete; workflows have clear steps.

**Code & scripts**
- [ ] Scripts solve rather than punt; explicit, helpful error handling.
- [ ] No voodoo constants; required packages listed and available.
- [ ] Forward slashes only; execution-vs-read intent explicit.
- [ ] Validation/feedback loops for critical or batch operations.

**Testing**
- [ ] At least three evaluation scenarios.
- [ ] Tested across the models you'll use (Haiku needs more guidance; Opus needs less hand-holding).
- [ ] Tested with real usage, both `/name` and automatic triggering; team feedback folded in if shared.
