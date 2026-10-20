#!/bin/bash

set -euo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

# The plugin's JS modules, plus Service.qml's admission, close and replay
# functions run against a fake ListModel and fake senders.
require_command node

if output=$(node "$SHELL_TEST_DIR/notifications/logic.cjs" 2>&1); then
  pass "notification logic holds its policies"
else
  fail "notification logic holds its policies" "$output"
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

service="$ROOT/shell/plugins/notifications/Service.qml"

# The startup step that makes the state directory and clears older layouts'
# leftovers, run as the service runs it, on a scratch HOME. It must keep the
# current files, never reach through a symlink, and leave the directory and
# the files the shell writes private.
prepare=$(node -e '
  const source = require("node:fs").readFileSync(process.argv[1], "utf8")
  const m = source.match(/id: storePrepare\s+command: \["bash", "-c",([^]*?),\s*"omarchy-notifications-state"/)
  process.stdout.write(require("node:vm").runInNewContext(m[1]))
' "$service")
state="$tmp/.local/state/omarchy/notifications"
mkdir -p "$state/live" "$state/history" "$state/images" "$state/icons" "$state/reply-demo" "$tmp/.cache/omarchy/notification-icons" "$tmp/outside"
touch "$state/live/n1.json" "$state/history/1-n1.json" "$state/1776000000000-7.json" "$state/policy.json" \
  "$state/.omarchy-notification-x1" "$state/reply-demo/notification.json" "$tmp/outside/keep.json" "$tmp/outside/1-2.json"
echo '[{"key":"n2"}]' >"$state/history.json"
chmod 644 "$state/history.json"
ln -s "$tmp/outside/keep.json" "$state/quiet.json"
ln -s "$tmp/outside" "$state/1-linked.json"
ln -s "$tmp/outside" "$state/images/outside"
bash -c "$prepare" omarchy-notifications-state "$state" "$tmp/.cache/omarchy/notification-icons" ||
  fail "the state directory is prepared"
left=$(cd "$state" && find . | sort | tr '\n' ' ')
[[ $left == ". ./1-linked.json ./history.json ./live.json ./quiet.json " ]] ||
  fail "older layouts' leftovers are cleared and nothing else" "$left"
[[ -f $tmp/outside/keep.json && -f $tmp/outside/1-2.json && ! -e $tmp/.cache/omarchy/notification-icons ]] ||
  fail "leftover cleanup never reaches through a symlink"
[[ $(cat "$state/history.json") == '[{"key":"n2"}]' && ! -L $state/quiet.json && ! -s $state/quiet.json ]] ||
  fail "current state is kept and a symlinked state file replaced"
[[ $(stat -c %a "$state" "$state/live.json" "$state/history.json" "$state/quiet.json" | tr '\n' ' ') == "700 600 600 600 " ]] ||
  fail "the state directory and its files are private"
pass "the state directory is prepared and older layouts cleared"

# Keybindings and commands call the notifications IPC target by method name.
# Every name they use must be one the service declares, or the key fires into
# "target not found".
declared=$(sed -n '/target: "notifications"/,/^  }/p' "$service" | grep -oE '^    function [A-Za-z]+' | awk '{print $2}' | sort -u)
used=$(
  {
    sed -nE 's/^ipc notifications\.([A-Za-z]+)$/\1/p' "$ROOT/default/omarchy/shortcuts"
    grep -rhoE 'ipc = "notifications\.[A-Za-z]+"' "$ROOT/default/hypr" | sed -E 's/.*notifications\.([A-Za-z]+)"/\1/'
    grep -rhoE 'omarchy-shell( -q)? notifications [A-Za-z]+' "$ROOT/bin" "$ROOT/install" "$ROOT/migrations" | awk '{print $NF}'
  } | sort -u
)
missing=$(comm -13 <(echo "$declared") <(echo "$used"))
[[ -z $missing ]] || fail "every notifications IPC method callers use is declared" "missing: $missing"
pass "every notifications IPC method callers use is declared"

# The surface keeps the namespace the glassy-window layer rule matches.
grep -q 'WlrLayershell.namespace: "omarchy-notifications"' "$service" ||
  fail "notification surface keeps the omarchy-notifications layer namespace"
grep -q 'omarchy-notifications' "$ROOT/default/hypr/toggles/window-glassy.lua" ||
  fail "glassy toggle still matches the notification layer namespace"
pass "notification surface keeps the omarchy-notifications layer namespace"
