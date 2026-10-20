#!/bin/bash

set -euo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

test_tmp=$(mktemp -d)
trap 'rm -rf "$test_tmp"' EXIT

migration="$ROOT/migrations/1792345511.sh"
mock_bin="$test_tmp/bin"
export TEST_LOG="$test_tmp/log"
mkdir -p "$mock_bin"

cat >"$mock_bin/omarchy-pkg-present" <<'SH'
#!/bin/bash
for pkg in "$@"; do
  [[ " $TEST_PACKAGES " == *" $pkg "* ]] || exit 1
done
SH
cat >"$mock_bin/omarchy-install-t3code-app" <<'SH'
#!/bin/bash
echo "install:$*" >>"$TEST_LOG"
SH
cat >"$mock_bin/omarchy-pkg-drop" <<'SH'
#!/bin/bash
echo "drop:$*" >>"$TEST_LOG"
SH
chmod +x "$mock_bin"/*

migrate() {
  : >"$TEST_LOG"
  TEST_PACKAGES="$1" HOME="$test_tmp/home" PATH="$mock_bin:$PATH" bash -euo pipefail "$migration" >"$test_tmp/output" 2>&1
}

fresh_home() {
  rm -rf "$test_tmp/home"
  mkdir -p "$test_tmp/home/.t3/userdata"
}

fresh_home
migrate "t3code-nightly-bin" || fail "migrating a nightly package succeeds" "$(cat "$test_tmp/output")"
[[ $(cat "$TEST_LOG") == "install:nightly" ]] || fail "the nightly package becomes the nightly app" "$(cat "$TEST_LOG")"
pass "the nightly package becomes the nightly app"

fresh_home
migrate "t3code-bin" || fail "migrating a stable package succeeds" "$(cat "$test_tmp/output")"
[[ $(cat "$TEST_LOG") == "install:stable" ]] || fail "the stable package becomes the stable app" "$(cat "$TEST_LOG")"
pass "the stable package becomes the stable app"

fresh_home
mkdir -p "$test_tmp/home/.local/share/t3code"
touch "$test_tmp/home/.local/share/t3code/T3-Code.AppImage"
migrate "t3code-bin" || fail "migrating next to an installed app succeeds" "$(cat "$test_tmp/output")"
[[ $(cat "$TEST_LOG") == "drop:t3code-bin t3code-nightly-bin" ]] || fail "only the leftover package goes" "$(cat "$TEST_LOG")"
pass "a user who already has the app only loses the leftover package"

rm -rf "$test_tmp/home"
mkdir -p "$test_tmp/home"
migrate "t3code-bin" || fail "migrating for a user who never ran T3 Code succeeds" "$(cat "$test_tmp/output")"
[[ ! -s $TEST_LOG ]] || fail "the package stays for the users who run T3 Code" "$(cat "$TEST_LOG")"
pass "a user who never ran T3 Code leaves the package for those who do"

fresh_home
migrate "" || fail "migrating without a T3 Code package succeeds" "$(cat "$test_tmp/output")"
[[ ! -s $TEST_LOG ]] || fail "nothing changes without a T3 Code package" "$(cat "$TEST_LOG")"
pass "nothing changes without a T3 Code package"

: >"$TEST_LOG"
cat >"$mock_bin/omarchy-install-t3code-app" <<'SH'
#!/bin/bash
exit 1
SH
fresh_home
if migrate "t3code-bin"; then
  fail "a failed app install keeps the migration pending"
fi
pass "a failed app install keeps the migration pending"
