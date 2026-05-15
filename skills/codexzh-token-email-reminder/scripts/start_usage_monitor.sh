#!/usr/bin/env zsh
set -euo pipefail

LABEL="${CODEXZH_USAGE_LABEL:-com.codexzh.usage-monitor}"
PLIST="${CODEXZH_USAGE_PLIST:-$HOME/Library/LaunchAgents/${LABEL}.plist}"
DOMAIN="gui/$(id -u)"

if [[ ! -f "$PLIST" ]]; then
  echo "LaunchAgent plist not found: $PLIST" >&2
  exit 1
fi

plutil -lint "$PLIST" >/dev/null

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  echo "$LABEL is already loaded"
else
  launchctl bootstrap "$DOMAIN" "$PLIST"
  echo "$LABEL loaded"
fi

launchctl print "$DOMAIN/$LABEL" | sed -n '1,80p'
