# Wrapping an API That Has No CLI

A recurring skill shape: an API (usually REST) has no official CLI or MCP server, but Claude needs to call it repeatedly. Bundle one script that exposes the high-frequency operations as readable subcommands plus a generic passthrough for everything else, then describe that surface in SKILL.md so Claude knows what to call and when.

## Contents
- When to use this pattern (and when not to)
- Anatomy: named subcommands + a generic passthrough
- Script structure
- Annotated example script
- Describing the interaction in SKILL.md
- Auth and secrets
- Output shaped for the model
- Robustness (errors, pagination, rate limits)

## When to use this pattern (and when not to)

Use it when **no existing tool fits**: the vendor ships no CLI, there's no MCP server, and Claude would otherwise hand-roll `curl` with the right auth headers on every call.

First check the alternatives — they're usually better if available:
- **An official CLI** (`gh`, `aws`, `stripe`) — use it directly; don't re-wrap it.
- **An MCP server** — prefer it for richer, typed interaction; reference tools as `ServerName:tool_name`.

Build a wrapper script only when those don't exist or don't cover what you need. The script turns "Claude reconstructs auth + base URL + JSON shaping each time" (fragile, token-heavy, inconsistent) into "Claude runs one documented command" (reliable, cheap, consistent) — exactly the payoff of [bundling scripts](best-practices.md).

## Anatomy: named subcommands + a generic passthrough

Two layers, mirroring the "one default with an escape hatch" principle:

1. **Abstracted subcommands** for the few highest-frequency operations — `get-issue`, `list-issues`, `create-issue`. These encode the path, method, and any output shaping so Claude (and you) read intent, not URLs.
2. **A generic `api <METHOD> <path> [body]` passthrough** that structurally invokes any endpoint. This is the escape hatch: you don't need a subcommand for every route, and Claude can reach endpoints you never anticipated.

Don't try to wrap the whole API. Wrap the 80% you use by name; let the passthrough cover the long tail.

## Script structure

- **Single entrypoint** (`scripts/api.sh`) that dispatches on `$1`. One file is easier to document and pre-approve than many.
- **`set -euo pipefail`** so failures surface instead of silently continuing.
- **Config from the environment**, never hardcoded: base URL with a sensible default, token from a documented env var. Fail loudly with a clear message if the token is missing.
- **All subcommands route through one core `api()` function** so auth, headers, and error handling live in exactly one place.
- **A `help` subcommand** listing the operations — discoverability. Claude can run `api.sh help` to learn the surface, and an unknown subcommand should print help to stderr and exit non-zero.
- **Surface HTTP status meaningfully.** On a non-2xx response, print the status and body to stderr and exit non-zero (`curl --fail-with-body` does this cleanly). Solve, don't punt — don't return a 500 body as if it were success.
- **Structured JSON to stdout**, diagnostics to stderr, so Claude can parse output and pipe it to `jq`.

## Annotated example script

`scripts/api.sh` — a thin wrapper over a fictional REST API:

```bash
#!/usr/bin/env bash
# Thin wrapper around the Example REST API.
#   Auth: EXAMPLE_API_TOKEN  (required)
#   Base: EXAMPLE_API_BASE   (optional; default https://api.example.com/v1)
set -euo pipefail

BASE="${EXAMPLE_API_BASE:-https://api.example.com/v1}"
: "${EXAMPLE_API_TOKEN:?Set EXAMPLE_API_TOKEN to a valid API token}"

# Core: every subcommand routes through here so auth + error handling live once.
# --fail-with-body exits non-zero on HTTP >=400 while still printing the body,
# so failures surface with their status instead of looking like success.
api() {
  local method="$1" path="$2" body="${3:-}"
  local args=(-sS --fail-with-body -X "$method"
    -H "Authorization: Bearer $EXAMPLE_API_TOKEN"
    -H "Content-Type: application/json")
  [[ -n "$body" ]] && args+=(-d "$body")
  curl "${args[@]}" "$BASE$path"
}

case "${1:-help}" in
  # --- Abstracted common operations --------------------------------
  get-issue)    api GET "/issues/$2" ;;
  list-issues)  api GET "/issues?state=${2:-open}" | jq '[.[] | {number, title, state}]' ;;
  create-issue) api POST "/issues" "$(jq -n --arg t "$2" --arg b "${3:-}" '{title:$t, body:$b}')" ;;

  # --- Generic escape hatch: call any endpoint directly ------------
  api)          api "$2" "$3" "${4:-}" ;;

  # --- Discoverability ---------------------------------------------
  help|*)
    cat >&2 <<'EOF'
Usage: api.sh <command> [args]
  get-issue <n>                 Fetch one issue as JSON
  list-issues [state]           List issues (default: open), trimmed to key fields
  create-issue <title> [body]   Create an issue
  api <METHOD> <path> [json]    Call any endpoint directly (escape hatch)
EOF
    [[ "${1:-}" == help ]] && exit 0 || exit 2 ;;
esac
```

Why the choices: env-var config keeps secrets out of the skill; the `api()` chokepoint means a header change touches one line; `jq` shaping in `list-issues` keeps responses small for context; the `*` case doubles as "unknown command" (exit 2) and `help` (exit 0).

## Describing the interaction in SKILL.md

The script is useless if Claude doesn't know the surface. In SKILL.md:

- **List each subcommand** with a one-line purpose, an example invocation, and the output shape. Reference the script via `${CLAUDE_SKILL_DIR}` so it resolves at any install location:
  ```markdown
  Interact with the Example API through `${CLAUDE_SKILL_DIR}/scripts/api.sh`.
  Requires `EXAMPLE_API_TOKEN` in the environment.

  - `api.sh get-issue <n>` — fetch one issue (JSON)
  - `api.sh list-issues [state]` — list issues, default `open`
  - `api.sh create-issue <title> [body]` — create an issue
  - `api.sh api <METHOD> <path> [json]` — any other endpoint

  Use a named subcommand when one exists; fall back to `api` for endpoints
  not covered above. Run `api.sh help` to see the current surface.
  ```
- **State execution intent**: "Run `api.sh get-issue 123`" — execute, not read. Only say "see the script" if Claude is meant to extend it.
- **Pre-approve with care.** `allowed-tools` lets read-only calls run without prompting; match how the command is actually invoked (e.g. `allowed-tools: Bash(*api.sh *)`). Consider leaving mutating subcommands (`create-*`, `delete-*`) to prompt, or split them so destructive operations aren't blanket-approved.

## Auth and secrets

- Read credentials from a **documented environment variable**; fail with an actionable message when unset (`: "${TOKEN:?Set TOKEN to ...}"`).
- **Never bundle credentials** in the skill or commit them. The skill names the variable; the user supplies the value.
- Claude Code skills have full network access, but say which hosts the script talks to so the interaction is auditable.

## Output shaped for the model

- **Emit JSON** so Claude can parse and re-query; reserve stderr for diagnostics.
- **Trim large responses** with `jq` projections or field/pagination flags — every returned field costs context. Offer a `--raw` path when full fidelity is occasionally needed.
- Keep output **stable and structured** across calls so Claude can rely on field names.

## Robustness (errors, pagination, rate limits)

- **Specific errors** beat generic failure: surface the HTTP status and response body so Claude can adjust rather than guess.
- **Pagination**: expose a page/cursor flag, or loop internally and concatenate — but cap output so it doesn't flood context.
- **Rate limits / transient failures**: retry with backoff inside the script. Justify the constants (`MAX_RETRIES=3  # most transient 5xx clear by the 2nd try`), never magic numbers.
- **Timeouts**: set a `curl --max-time` with a documented value.
