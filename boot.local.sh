#!/bin/bash

ansi_art='                 ▄▄▄
 ▄█████▄    ▄███████████▄    ▄███████   ▄███████   ▄███████   ▄█   █▄    ▄█   █▄
███   ███  ███   ███   ███  ███   ███  ███   ███  ███   ███  ███   ███  ███   ███
███   ███  ███   ███   ███  ███   ███  ███   ███  ███   █▀   ███   ███  ███   ███
███   ███  ███   ███   ███ ▄███▄▄▄███ ▄███▄▄▄██▀  ███       ▄███▄▄▄███▄ ███▄▄▄███
███   ███  ███   ███   ███ ▀███▀▀▀███ ▀███▀▀▀▀    ███      ▀▀███▀▀▀███  ▀▀▀▀▀▀███
███   ███  ███   ███   ███  ███   ███ ██████████  ███   █▄   ███   ███  ▄██   ███
███   ███  ███   ███   ███  ███   ███  ███   ███  ███   ███  ███   ███  ███   ███
 ▀█████▀    ▀█   ███   █▀   ███   █▀   ███   ███  ███████▀   ███   █▀    ▀█████▀
                                       ███   █▀                                  '

clear
echo -e "\n$ansi_art\n"

sudo pacman -Syu --noconfirm --needed git gum

# Use custom repo if specified, otherwise default to basecamp/omarchy
OMARCHY_REPO="${OMARCHY_REPO:-basecamp/nomarchy}"

# echo -e "\nCloning Omarchy from: https://github.com/${OMARCHY_REPO}.git"

rm -rf ~/.local/share/omarchy
mkdir -p ~/.local/share
# git clone "https://github.com/${OMARCHY_REPO}.git" ~/.local/share/omarchy >/dev/null


# Get absolute path of the script's directory
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# Create symlink
ln -sfn "$SCRIPT_DIR" "$HOME/.local/share/omarchy"

# Use custom branch if instructed, otherwise default to master
OMARCHY_REF="${OMARCHY_REF:-master}"
if [[ $OMARCHY_REF != "master" ]]; then
  echo -e "\eUsing branch: $OMARCHY_REF"
  cd ~/.local/share/omarchy
  git fetch origin "${OMARCHY_REF}" && git checkout "${OMARCHY_REF}"
  cd -
fi

# Interactive mode selection
echo "🔧 Installation mode:"
if gum confirm "Use interactive mode? (Confirm each application group)"; then
    export OMARCHY_INTERACTIVE=true
    echo "✓ Interactive mode enabled"
else
    export OMARCHY_INTERACTIVE=false
    echo "✓ Automatic installation mode"
fi

echo
# Window manager selection
echo "🪟 Window manager selection:"
WM_CHOICE=$(gum choose "Hyprland (default)" "Niri (scrollable tiling)")

if echo "$WM_CHOICE" | grep -q "Niri"; then
    export OMARCHY_WM=niri
    echo "✓ Niri selected (scrollable tiling compositor)"
else
    export OMARCHY_WM=hyprland
    echo "✓ Hyprland selected (traditional tiling)"
fi

echo -e "\nInstallation starting..."
echo "Mode: $([ "$OMARCHY_INTERACTIVE" = "true" ] && echo "Interactive" || echo "Automatic")"
echo "Window Manager: $OMARCHY_WM"
echo
source ~/.local/share/omarchy/install.sh
