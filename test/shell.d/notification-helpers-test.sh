#!/bin/bash

set -euo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

# The notification service's Python helpers (shell/plugins/notifications/helpers):
# the sandbox launcher, the store and the KDE Connect bridge. The unit tests
# live in notifications/ as Python unittest modules; tap.py runs them and prints
# one ok/SKIP/not ok line per test. Checks that need Bubblewrap skip themselves
# when it is missing.

require_command python3

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home" "$tmp/work"

# Every helper and test resolves state from HOME; none may reach the real
# ~/.local/state or ~/.config, and none inherits a sandbox policy.
if ! (
  cd "$tmp/work"
  env -u OMARCHY_NOTIFICATIONS_REQUIRE_SANDBOX -u PYTHONPATH \
    HOME="$tmp/home" PYTHONDONTWRITEBYTECODE=1 \
    XDG_STATE_HOME="$tmp/home/.local/state" \
    XDG_CONFIG_HOME="$tmp/home/.config" \
    XDG_CACHE_HOME="$tmp/home/.cache" \
    python3 -B "$SHELL_TEST_DIR/notifications/tap.py"
); then
  fail "notification helper unit tests pass"
fi

[[ -z $(find "$ROOT/shell/plugins/notifications/helpers" "$SHELL_TEST_DIR/notifications" -name __pycache__) ]] ||
  fail "notification helper tests leave no bytecode in the checkout"

pass "notification helper unit tests pass"
