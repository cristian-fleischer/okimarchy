#!/bin/bash

abort() {
  echo -e "\e[31mOmarchy install requires: $1\e[0m"
  echo
  gum confirm "Proceed anyway on your own accord and without assistance?" || exit 1
}

# Must be an Arch distro
[[ -f /etc/arch-release ]] || abort "Vanilla Arch"

# Must not be an Arch derivative distro
for marker in /etc/cachyos-release /etc/eos-release /etc/garuda-release /etc/manjaro-release; do
  [[ -f "$marker" ]] && abort "Vanilla Arch"
done

# Must not be running as root
[ "$EUID" -eq 0 ] && abort "Running as root (not user)"

# Must be x86 only to fully work
[ "$(uname -m)" != "x86_64" ] && abort "x86_64 CPU"

# Check for existing desktop environments
if pacman -Qe gnome-shell &>/dev/null; then
    if [[ "$OMARCHY_INSTALL_MODE" != "overlay" ]]; then
        abort "Fresh + Vanilla Arch (or set OMARCHY_FORCE_OVERLAY=true for overlay installation)"
    else
        echo "⚠️  GNOME detected - installing in overlay mode"
    fi
fi

if pacman -Qe plasma-desktop &>/dev/null; then
    if [[ "$OMARCHY_INSTALL_MODE" != "overlay" ]]; then
        abort "Fresh + Vanilla Arch (or set OMARCHY_FORCE_OVERLAY=true for overlay installation)"
    else
        echo "⚠️  KDE Plasma detected - installing in overlay mode"
    fi
fi

# Cleared all guards
echo "Guards: OK"
