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

# The KDE Connect reply bridge, in a scratch HOME so its demo fixture paths
# never reach the real ~/.local/state.
require_command python3
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
if output=$(cd "$tmp" && HOME="$tmp" python3 -I -B "$SHELL_TEST_DIR/notifications/kdeconnect-test.py" 2>&1); then
  pass "the KDE Connect reply bridge matches and replies safely"
else
  fail "the KDE Connect reply bridge matches and replies safely" "$output"
fi
[[ -z $(find "$ROOT/shell/plugins/notifications/helpers" -name __pycache__) ]] ||
  fail "the KDE Connect test leaves no bytecode in the checkout"

service="$ROOT/shell/plugins/notifications/Service.qml"

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

# The helpers the service runs are the ones that ship beside it.
for helper in store kdeconnect; do
  [[ -x $ROOT/shell/plugins/notifications/helpers/$helper ]] ||
    fail "notification helper $helper is executable"
done
pass "notification helpers ship executable"
