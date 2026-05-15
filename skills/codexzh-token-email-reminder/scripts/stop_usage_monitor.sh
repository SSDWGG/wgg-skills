#!/usr/bin/env zsh
set -euo pipefail

LABEL="${CODEXZH_USAGE_LABEL:-com.codexzh.usage-monitor}"
DOMAIN="gui/$(id -u)"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/$LABEL"
  echo "$LABEL unloaded"
else
  echo "$LABEL is not loaded"
fi
