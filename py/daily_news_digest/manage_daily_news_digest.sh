#!/usr/bin/env bash
set -euo pipefail

LABEL="com.news-digest.daily"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/daily_news_digest.py"
EMAIL_SCRIPT="$SCRIPT_DIR/send_email_with_attachment_via_email_mcp.mjs"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_VALUE="$(id -u)"

EMAIL_ACCOUNT="${NEWS_DIGEST_EMAIL_ACCOUNT:-1982549567@qq.com}"
EMAIL_TO="${NEWS_DIGEST_EMAIL_TO:-$EMAIL_ACCOUNT}"

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
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>10</integer></dict>
    <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>40</integer></dict>
  </array>
  <key>WorkingDirectory</key>
  <string>$HOME</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>NEWS_DIGEST_EMAIL_ACCOUNT</key>
    <string>$EMAIL_ACCOUNT</string>
    <key>NEWS_DIGEST_EMAIL_TO</key>
    <string>$EMAIL_TO</string>
    <key>NEWS_DIGEST_SEND_EMAIL_SCRIPT</key>
    <string>$EMAIL_SCRIPT</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key>
  <string>$HOME/.codex/log/daily-news-digest.out.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.codex/log/daily-news-digest.err.log</string>
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
  NEWS_DIGEST_SEND_EMAIL_SCRIPT="$EMAIL_SCRIPT" /usr/bin/python3 "$PYTHON_SCRIPT" --force-email
}

case "${1:-start}" in
  start|resume|schedule)
    write_plist
    reload_agent
    status_agent
    send_start_test
    ;;
  run)
    NEWS_DIGEST_SEND_EMAIL_SCRIPT="$EMAIL_SCRIPT" /usr/bin/python3 "$PYTHON_SCRIPT"
    ;;
  morning)
    NEWS_DIGEST_SEND_EMAIL_SCRIPT="$EMAIL_SCRIPT" /usr/bin/python3 "$PYTHON_SCRIPT" --digest-name morning
    ;;
  evening)
    NEWS_DIGEST_SEND_EMAIL_SCRIPT="$EMAIL_SCRIPT" /usr/bin/python3 "$PYTHON_SCRIPT" --digest-name evening
    ;;
  dry-run)
    NEWS_DIGEST_SEND_EMAIL_SCRIPT="$EMAIL_SCRIPT" /usr/bin/python3 "$PYTHON_SCRIPT" --dry-run
    ;;
  stop|pause)
    launchctl bootout "gui/$UID_VALUE" "$PLIST" 2>/dev/null || true
    echo "$LABEL stopped"
    ;;
  status)
    status_agent
    ;;
  *)
    echo "Usage: $0 {start|resume|schedule|run|morning|evening|dry-run|stop|pause|status}" >&2
    exit 2
    ;;
esac
