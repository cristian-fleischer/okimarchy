#!/bin/bash

# Install build tools
sudo pacman -S --needed --noconfirm base-devel

# Configure pacman - preserve existing repositories and add omarchy repo
echo "📦 Configuring pacman repositories..."

# Backup existing pacman.conf
sudo cp /etc/pacman.conf /etc/pacman.conf.omarchy-backup

# Check if omarchy repository is already configured
if ! grep -q "\[omarchy\]" /etc/pacman.conf; then
    echo "   Adding omarchy repository..."
    # Add omarchy repository to existing config
    sudo tee -a /etc/pacman.conf > /dev/null << 'EOF'

[omarchy]
SigLevel = Optional TrustAll
Server = https://pkgs.omarchy.org/$arch
EOF
else
    echo "   Omarchy repository already configured"
fi

# Only update mirrorlist if it doesn't exist or is default
if [[ ! -f /etc/pacman.d/mirrorlist ]] || [[ $(wc -l < /etc/pacman.d/mirrorlist) -lt 5 ]]; then
    echo "   Updating mirrorlist (was minimal/missing)..."
    sudo cp -f ~/.local/share/omarchy/default/pacman/mirrorlist /etc/pacman.d/mirrorlist
else
    echo "   Keeping existing mirrorlist (looks customized)"
fi

# Refresh all repos
sudo pacman -Syu --noconfirm
