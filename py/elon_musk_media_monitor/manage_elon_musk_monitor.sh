#!/usr/bin/env bash
set -euo pipefail

LABEL="com.social-monitoring.elon-musk-media"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/elon_musk_media_monitor.py"
EMAIL_SCRIPT="$SCRIPT_DIR/send_email_with_attachment_via_email_mcp.mjs"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_VALUE="$(id -u)"

EMAIL_ACCOUNT="${ELON_MONITOR_EMAIL_ACCOUNT:-1982549567@qq.com}"
EMAIL_TO="${ELON_MONITOR_EMAIL_TO:-$EMAIL_ACCOUNT}"

write_plist() {
  local interval="$1"
  local run_at_load="$2"

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
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ELON_MONITOR_EMAIL_ACCOUNT</key>
    <string>$EMAIL_ACCOUNT</string>
    <key>ELON_MONITOR_EMAIL_TO</key>
    <string>$EMAIL_TO</string>
    <key>ELON_MONITOR_SEND_EMAIL_SCRIPT</key>
    <string>$EMAIL_SCRIPT</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key>
  <$run_at_load/>
  <key>StartInterval</key>
  <integer>$interval</integer>
  <key>WorkingDirectory</key>
  <string>$HOME</string>
  <key>StandardOutPath</key>
  <string>$HOME/.codex/log/elon-musk-media-monitor.out.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.codex/log/elon-musk-media-monitor.err.log</string>
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
  launchctl print "gui/$UID_VALUE/$LABEL" 2>/dev/null | rg 'state =|runs =|last exit code|run interval|path =' || {
    echo "$LABEL is not loaded"
  }
}

send_start_test() {
  echo "Sending startup test email to $EMAIL_TO ..."
  ELON_MONITOR_SEND_EMAIL_SCRIPT="$EMAIL_SCRIPT" /usr/bin/python3 "$PYTHON_SCRIPT" --force-email
}

case "${1:-start}" in
  start)
    write_plist 21600 false
    reload_agent
    status_agent
    send_start_test
    ;;
  test-minute)
    write_plist 60 true
    reload_agent
    status_agent
    send_start_test
    ;;
  six-hours)
    write_plist 21600 false
    reload_agent
    status_agent
    send_start_test
    ;;
  run)
    ELON_MONITOR_SEND_EMAIL_SCRIPT="$EMAIL_SCRIPT" /usr/bin/python3 "$PYTHON_SCRIPT" --force-email
    ;;
  dry-run)
    ELON_MONITOR_SEND_EMAIL_SCRIPT="$EMAIL_SCRIPT" /usr/bin/python3 "$PYTHON_SCRIPT" --dry-run
    ;;
  stop)
    launchctl bootout "gui/$UID_VALUE" "$PLIST" 2>/dev/null || true
    echo "$LABEL stopped"
    ;;
  status)
    status_agent
    ;;
  *)
    echo "Usage: $0 {start|test-minute|six-hours|run|dry-run|stop|status}" >&2
    exit 2
    ;;
esac
