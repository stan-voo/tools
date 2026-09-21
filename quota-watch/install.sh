#!/bin/bash
# Install quota-watch as a macOS LaunchAgent that ticks hourly.
#
#   ./install.sh            write the agent and load it (runs one tick at once)
#   ./install.sh --print    print the plist it would write, change nothing
#   ./install.sh --remove   unload the agent and delete its plist
#
# Settings (Telegram and the rest) go in ~/.config/quota-watch/env, not here:
# launchd starts the job without your shell's environment.

set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
label="${QUOTA_WATCH_LABEL:-local.quota-watch}"
plist="$HOME/Library/LaunchAgents/$label.plist"
state="${XDG_STATE_HOME:-$HOME/.local/state}/quota-watch"
python="${PYTHON:-$(command -v python3 || true)}"
domain="gui/$(id -u)"

[ -n "$python" ] || { echo "python3 not found; set PYTHON=/path/to/python3" >&2; exit 1; }

render() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
        <string>$python</string>
        <string>$here/quota_watch.py</string>
        <string>tick</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$state/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$state/launchd.log</string>
</dict>
</plist>
EOF
}

case "${1:-}" in
  --print)
    render
    ;;
  --remove)
    launchctl bootout "$domain/$label" 2>/dev/null || true
    rm -f "$plist"
    echo "removed $label (history stays in $state)"
    ;;
  "")
    mkdir -p "$state" "$(dirname "$plist")"
    launchctl bootout "$domain/$label" 2>/dev/null || true
    render > "$plist"
    plutil -lint "$plist" >/dev/null
    launchctl bootstrap "$domain" "$plist"
    echo "loaded $label: hourly, log at $state/launchd.log"
    ;;
  *)
    sed -n '2,8p' "$0" >&2
    exit 2
    ;;
esac
