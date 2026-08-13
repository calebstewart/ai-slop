# Task: severity-classify and label open GitHub issues

You are classifying issues in `{{REPO}}` so a downstream loop can rank them. This is a
fast labelling pass — **do not read the codebase, do not clone anything, do not run
anything.** Judge only from the title, labels, and body text you are given.

Give every issue two things: a **severity category** and a **short summary**. Then group
the ones that would collide if they were fixed at the same time.

## Severity category

Assign every issue exactly one:

| Category | Meaning |
|---|---|
| `1` | Security vulnerability — XSS, injection, path traversal, unsafe deserialization, secret leakage, privilege issues |
| `2` | Crash, panic, hang, infinite loop, unbounded memory/CPU growth, deadlock |
| `3` | Correctness bug — wrong output, malformed output, silently dropped or mangled data |
| `4` | CI, tooling, build, packaging, or release-process defect |
| `5` | Docs, metadata, help text, comments, cosmetics |

Rules:

- **Classify by the described impact, not by the title's framing.** An issue titled
  "docs: help text is inaccurate" is category 5, but "help text says the flag requires
  a prefix and it silently drops input when you omit it" describes wrong behavior and
  is category 3.
- Feature requests and enhancements take the category of the problem they solve; if
  they solve no defect, use `5`.
- When two categories genuinely fit, choose the **more severe** (lower number). A
  later Opus planner reads the actual code and can correct you downward; nothing else
  in the pipeline corrects an under-estimate, and the category also decides how
  rigorously the eventual fix gets reviewed.
- If a body is empty or unintelligible, use `3` — unknown is not the same as harmless.

## Short summary

Two to five words naming **the specific defect**, used to label the sub-agents that
will work the issue (they appear as "Planning #12: seek offset overflow"). So:

- Name the thing that is wrong, not the action to take: `seek offset overflow`, not
  `fix the seek bug`.
- Be specific enough to tell two issues apart at a glance. `parser crash` is weak if
  three issues are parser crashes; `parser crash on empty input` distinguishes it.
- Lowercase except for identifiers that are genuinely capitalized. No trailing period,
  no issue number, no category word, no quotes, no colons.
- If the title is already a good summary, compressing it is fine — do not invent
  detail the issue does not state.

## Clusters

Two issues that would be fixed **in the same files** must not be worked at the same
time: whichever lands second gets rebased, re-reviewed, and often re-planned, which
costs far more than the parallelism saves. So group them, and the loop will run them one
after another.

Group **only on likely file overlap**, judged from the evidence in front of you — the
same component, module, command, or file named in the titles and bodies. Do not group on
topical similarity: "two parser bugs" is a cluster only if they plainly touch the same
parser code; two independent crashes in different subsystems are not, and neither are
"three documentation issues" about unrelated docs.

Most issues belong to no cluster. Emitting no cluster lines at all is a perfectly good
answer; grouping everything is not, because it serializes the entire queue.

## Issues to classify

{{FILE:{{INPUT_FILE}}}}

## Output

Write a file at exactly this path:

    {{OUT_FILE}}

with one line per issue and nothing else — no prose, no markdown, no code fence:

    <issue-number>: <category-digit>: <short summary>

For example:

    12: 3: seek offset overflow past EOF
    29: 4: release workflow skips arm64
    31: 1: path traversal in archive extract

Then, **after** those lines, zero or more cluster lines — a short lowercase key naming
the shared area, followed by the issue numbers in it:

    CLUSTER: html-escaping 12 47
    CLUSTER: release-workflow 29 30 33

Only issues that share a cluster with another issue belong on these lines; never write a
cluster with a single member.

Every issue number listed above must appear exactly once among the per-issue lines. Your
final message should be just the word `done` — the file is the deliverable.
