echo "Move notifications to the new notification engine and retire the Omapager plugin"

# The notification helpers run under Bubblewrap when it is available.
omarchy-pkg-add bubblewrap

state="$HOME/.local/state/omarchy"
root="$state/notifications"
mkdir -p "$root"

# Omapager kept the same store under its own name, so its history, held
# notifications, quiet state and icon cache move over as they are. Nothing
# already in the new store is overwritten. The old engine's popup files and
# image copies are left for the store, which drops what it cannot read.
omapager="$state/omapager"
if [[ -d $omapager && ! -L $omapager ]]; then
  for dir in live history icons reply-demo; do
    [[ -d $omapager/$dir ]] || continue
    mkdir -p "$root/$dir"
    find "$omapager/$dir" -mindepth 1 -maxdepth 1 -exec mv -n -t "$root/$dir" {} +
    rmdir "$omapager/$dir" 2>/dev/null || true
  done
  for file in quiet.json policy.json; do
    if [[ -f $omapager/$file ]]; then
      mv -n "$omapager/$file" "$root/$file"
    fi
  done
  rmdir "$omapager" 2>/dev/null || true
fi

# The old engine kept Do Not Disturb in its own settings file. Carry it over
# unless the new quiet state already exists.
legacy_settings="$state/notifications.json"
if [[ -f $legacy_settings ]]; then
  if [[ ! -e $root/quiet.json ]] && jq -e '.dnd == true' "$legacy_settings" >/dev/null 2>&1; then
    jq -n --argjson since "$(date +%s)" '{snoozes: {}, dnd: true, silencedSince: $since}' >"$root/quiet.json"
    chmod 600 "$root/quiet.json"
  fi
  rm -f "$legacy_settings"
fi

# Omapager ran as a bar widget beside a disabled omarchy.notifications. Its
# settings move into shell.json's notifications object, its widget leaves the
# bar, and the built-in service comes back on. A built-in service someone
# disabled for another daemon stays disabled.
config_file="$HOME/.config/omarchy/shell.json"
if [[ -s $config_file ]] && jq -e '
  [.bar.layout[]?[]?, .plugins[]?] | map(if type == "object" then .id else . end) | index("njpatel.omapager")
' "$config_file" >/dev/null 2>&1; then
  tmp=$(mktemp)
  jq '
    def omapager: (type == "object" and .id == "njpatel.omapager") or . == "njpatel.omapager";
    ([.bar.layout[]?[]?, .plugins[]?] | map(select(type == "object" and .id == "njpatel.omapager")) | first // {}) as $entry
    | ($entry | del(.id, .alwaysShow)) as $settings
    | .notifications = ($settings + (if (.notifications | type) == "object" then .notifications else {} end))
    | if (.bar.layout | type) == "object" then .bar.layout |= map_values(if type == "array" then map(select(omapager | not)) end) end
    | if (.plugins | type) == "array" then .plugins |= map(select(omapager | not)) end
    | if (.disabledPlugins | type) == "array" then .disabledPlugins |= map(select(. != "omarchy.notifications")) end
  ' "$config_file" >"$tmp"
  mv "$tmp" "$config_file"
  echo "Omapager is now part of Omarchy. Remove its checkout with: omarchy plugin remove njpatel.omapager"
fi
