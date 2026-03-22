#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

DEFAULTS="$SKILL_DIR/references/defaults.yaml"
SPECRC="specs/.specrc.yaml"

if [[ ! -f "$DEFAULTS" ]]; then
  echo "# ERROR: defaults.yaml not found at $DEFAULTS" >&2
  exit 1
fi

if command -v yq &>/dev/null; then
  if [[ -f "$SPECRC" ]]; then
    yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' "$DEFAULTS" "$SPECRC"
  else
    yq eval '.' "$DEFAULTS"
  fi
else
  echo "# WARNING: yq not found — outputting raw defaults without merge" >&2
  cat "$DEFAULTS"
fi