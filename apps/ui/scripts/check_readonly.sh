#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT_DIR"

UNSTAGED_OUTSIDE="$(git diff --name-only -- . ':(exclude)apps/ui/**')"
STAGED_OUTSIDE="$(git diff --cached --name-only -- . ':(exclude)apps/ui/**')"
UNTRACKED_OUTSIDE="$(git ls-files --others --exclude-standard -- . ':(exclude)apps/ui/**')"

OUTSIDE_COMBINED="$(printf '%s\n%s\n%s\n' "$UNSTAGED_OUTSIDE" "$STAGED_OUTSIDE" "$UNTRACKED_OUTSIDE" | sed '/^$/d' | sort -u)"

if [[ -n "$OUTSIDE_COMBINED" ]]; then
  echo "ERROR: Changes detected outside apps/ui:" >&2
  echo "$OUTSIDE_COMBINED" >&2
  exit 1
fi

echo "OK: Only apps/ui/ has changes."
