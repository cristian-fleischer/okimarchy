echo "Replace the T3 Code package with the T3 Code app, which updates itself"

if omarchy-pkg-present t3code-nightly-bin; then
  channel="nightly"
elif omarchy-pkg-present t3code-bin; then
  channel="stable"
else
  exit 0
fi

# The package is installed for the whole machine, but only a user who has run
# T3 Code has anything to carry over. Leave it in place for whoever does.
if [[ ! -d $HOME/.t3 && ! -d $HOME/.config/t3code && ! -d $HOME/.config/t3code-v2 ]]; then
  exit 0
fi

if [[ -f $HOME/.local/share/t3code/T3-Code.AppImage ]]; then
  omarchy-pkg-drop t3code-bin t3code-nightly-bin
else
  # Threads, settings, and the theme stay in ~/.t3, which the app keeps using.
  omarchy-install-t3code-app "$channel"
fi

echo "T3 Code now updates itself. If it is open, quit and reopen it to run the new app."
