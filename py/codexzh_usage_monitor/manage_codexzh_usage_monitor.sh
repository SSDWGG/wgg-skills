#!/usr/bin/env bash
set -euo pipefail

LABEL="com.codexzh.usage-monitor"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNAPSHOT_SCRIPT="$SCRIPT_DIR/codexzh_usage_snapshot.py"
QUERY_SCRIPT="$SCRIPT_DIR/query_codexzh_usage.py"
EMAIL_SCRIPT="$SCRIPT_DIR/send_email_via_email_mcp.mjs"
RUNTIME_DIR="$HOME/.codex/scripts/codexzh_usage_monitor"
RUNTIME_SHARED_DIR="$HOME/.codex/scripts/_shared"
RUNTIME_SNAPSHOT_SCRIPT="$RUNTIME_DIR/codexzh_usage_snapshot.py"
RUNTIME_QUERY_SCRIPT="$RUNTIME_DIR/query_codexzh_usage.py"
RUNTIME_EMAIL_SCRIPT="$RUNTIME_DIR/send_email_via_email_mcp.mjs"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_VALUE="$(id -u)"

EMAIL_ACCOUNT="${CODEXZH_EMAIL_ACCOUNT:-1982549567@qq.com}"
EMAIL_TO="${CODEXZH_EMAIL_TO:-$EMAIL_ACCOUNT}"

install_runtime_scripts() {
  mkdir -p "$RUNTIME_DIR" "$RUNTIME_SHARED_DIR" "$HOME/.codex/log"
  cp "$SNAPSHOT_SCRIPT" "$RUNTIME_SNAPSHOT_SCRIPT"
  cp "$QUERY_SCRIPT" "$RUNTIME_QUERY_SCRIPT"
  cp "$EMAIL_SCRIPT" "$RUNTIME_EMAIL_SCRIPT"
  cp "$SCRIPT_DIR/../_shared/net_fetch.py" "$RUNTIME_SHARED_DIR/net_fetch.py"
  chmod 755 "$RUNTIME_SNAPSHOT_SCRIPT" "$RUNTIME_QUERY_SCRIPT" "$RUNTIME_EMAIL_SCRIPT"
}

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
    <string>$RUNTIME_SNAPSHOT_SCRIPT</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
  </array>
  <key>WorkingDirectory</key>
  <string>$HOME</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>CODEXZH_USAGE_QUERY_SCRIPT</key>
    <string>$RUNTIME_QUERY_SCRIPT</string>
    <key>CODEXZH_SEND_EMAIL_SCRIPT</key>
    <string>$RUNTIME_EMAIL_SCRIPT</string>
    <key>CODEXZH_EMAIL_ACCOUNT</key>
    <string>$EMAIL_ACCOUNT</string>
    <key>CODEXZH_EMAIL_TO</key>
    <string>$EMAIL_TO</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key>
  <string>$HOME/.codex/log/codexzh-usage-monitor.out.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.codex/log/codexzh-usage-monitor.err.log</string>
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

send_start_test() {
  echo "Sending startup test email to $EMAIL_TO ..."
  /usr/bin/python3 "$RUNTIME_SNAPSHOT_SCRIPT" --force-email
}

case "${1:-start}" in
  start|resume|schedule)
    install_runtime_scripts
    write_plist
    reload_agent
    status_agent
    send_start_test
    ;;
  run)
    install_runtime_scripts
    /usr/bin/python3 "$RUNTIME_SNAPSHOT_SCRIPT"
    ;;
  force-email)
    install_runtime_scripts
    /usr/bin/python3 "$RUNTIME_SNAPSHOT_SCRIPT" --force-email
    ;;
  query)
    install_runtime_scripts
    /usr/bin/python3 "$RUNTIME_QUERY_SCRIPT" --json
    ;;
  stop|pause)
    launchctl bootout "gui/$UID_VALUE" "$PLIST" 2>/dev/null || true
    echo "$LABEL stopped"
    ;;
  status)
    status_agent
    ;;
  *)
    echo "Usage: $0 {start|resume|schedule|run|force-email|query|stop|pause|status}" >&2
    exit 2
    ;;
esac
