#!/usr/bin/env bash
set -euo pipefail

LABEL="com.gh-pr-bot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/main.py"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_VALUE="$(id -u)"

write_plist() {
  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.codex/log"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$PYTHON_SCRIPT</string>
    <string>auto</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>7</integer></dict>
  <key>WorkingDirectory</key>
  <string>$HOME</string>
  <key>StandardOutPath</key>
  <string>$HOME/.codex/log/gh-pr-bot.out.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.codex/log/gh-pr-bot.err.log</string>
</dict>
</plist>
PLIST
  plutil -lint "$PLIST" >/dev/null
}

reload_agent() {
  launchctl bootout "gui/$UID_VALUE" "$PLIST" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_VALUE" "$PLIST"
}

status_agent() {
  launchctl print "gui/$UID_VALUE/$LABEL" 2>/dev/null | rg 'path =|state =|runs =|last exit code|calendar interval|stdout path|stderr path' || {
    echo "$LABEL is not loaded"
  }
}

case "${1:-start}" in
  start|schedule)
    write_plist
    reload_agent
    status_agent
    ;;
  scan)
    /usr/bin/python3 "$PYTHON_SCRIPT" scan
    ;;
  submit)
    /usr/bin/python3 "$PYTHON_SCRIPT" submit
    ;;
  status)
    /usr/bin/python3 "$PYTHON_SCRIPT" status
    ;;
  auto)
    /usr/bin/python3 "$PYTHON_SCRIPT" auto
    ;;
  report)
    /usr/bin/python3 "$PYTHON_SCRIPT" report
    ;;
  dry-run)
    /usr/bin/python3 "$PYTHON_SCRIPT" auto --dry-run
    ;;
  stop|pause)
    launchctl bootout "gui/$UID_VALUE" "$PLIST" 2>/dev/null || true
    echo "$LABEL stopped"
    ;;
  *)
    echo "Usage: $0 {start|scan|submit|status|auto|report|dry-run|stop|status}" >&2
    exit 2
    ;;
esac
