#!/usr/bin/env bash
# PostToolUse hook: auto-format and lint-fix a changed Python file.
# Receives the tool payload as JSON on stdin; formats only .py files.
set -euo pipefail

payload=$(cat)
file=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')

# Nothing to do for non-Python or missing paths.
[ -z "$file" ] && exit 0
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

# Format then autofix. Run from the project dir so uv resolves the right env.
cd "${CLAUDE_PROJECT_DIR:-.}"
uv run ruff format "$file"
uv run ruff check --fix "$file"
