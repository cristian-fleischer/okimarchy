echo "Leave mise's upgrade pruning setting to Omarchy's config instead of the user's"

# Setup and an earlier migration wrote upgrade.auto_prune = false into the
# user's mise config. The settings package ships it in /etc/mise/conf.d now, so
# that copy only clutters a file that is the user's. A different value is the
# user's choice and stays.
mise_config="$HOME/.config/mise/config.toml"

if [[ -f $mise_config ]] && [[ $(mise config get -f "$mise_config" settings.upgrade.auto_prune 2>/dev/null) == "false" ]]; then
  mise settings unset upgrade.auto_prune
fi
