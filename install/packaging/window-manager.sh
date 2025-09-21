#!/bin/bash

# Window Manager specific package installation
# Handles Hyprland vs Niri package differences
# 
# Note: We disable mako's systemd service because both Hyprland and Niri
# start mako directly through their configuration files. This prevents 
# mako from interfering with other desktop environments like KDE Plasma.

# Default to Hyprland if not specified
OMARCHY_WM=${OMARCHY_WM:-hyprland}

echo "🪟 Installing $OMARCHY_WM window manager and related packages..."

if [[ "$OMARCHY_WM" == "niri" ]]; then
    echo "📦 Installing Niri ecosystem..."

    # Niri specific packages
    NIRI_PACKAGES=(
        "niri"
        "walker-bin"       # Application launcher (same as hyprland)
        "mako"             # notification daemon
        "swaylock"         # Screen locker
        "swayidle"         # Idle management
        "swaybg"           # Background setter
        "swayosd"          # On-screen display
        "waybar"           # Status bar
        "wl-clipboard"     # Clipboard utilities
        "wl-clip-persist"  # Clipboard persistence
        "slurp"            # Screen selection
        "grim"             # Screenshot utility
        "xdg-desktop-portal-gtk"     # Desktop portal
        "xdg-desktop-portal-gnome"   # Additional portal support
        "qt5-wayland"      # Qt Wayland support
        "xwayland-satellite"         # XWayland support
    )

    echo "   Installing niri core packages..."
    if sudo pacman -S --noconfirm --needed "${NIRI_PACKAGES[@]}"; then
        echo "✅ Niri packages installed successfully"
    else
        echo "❌ Failed to install some niri packages"
        exit 1
    fi

    # Disable mako systemd service - niri will start it directly
    echo "   Disabling mako systemd service (niri will manage it)"
    systemctl --user disable mako.service 2>/dev/null || true
    systemctl --user stop mako.service 2>/dev/null || true

    # Store WM choice for other scripts
    mkdir -p ~/.local/state/omarchy
    echo "niri" > ~/.local/state/omarchy/current-wm

elif [[ "$OMARCHY_WM" == "hyprland" ]]; then
    echo "📦 Installing Hyprland ecosystem..."

    # Hyprland specific packages
    HYPRLAND_PACKAGES=(
        "hyprland"
        "hyprland-qtutils"
        "hypridle"
        "hyprlock"
        "hyprpicker"
        "hyprshot"
        "hyprsunset"
        "waybar"           # Status bar
        "mako"             # Notification daemon
        "swaybg"           # Background setter
        "swayosd"          # On-screen display
        "walker-bin"       # Application launcher
        "wl-clipboard"     # Clipboard utilities
        "wl-clip-persist"  # Clipboard persistence
        "slurp"            # Screen selection
        "xdg-desktop-portal-hyprland"  # Hyprland portal
        "xdg-desktop-portal-gtk"       # GTK portal
        "qt5-wayland"      # Qt Wayland support
    )

    echo "   Installing hyprland core packages..."
    if sudo pacman -S --noconfirm --needed "${HYPRLAND_PACKAGES[@]}"; then
        echo "✅ Hyprland packages installed successfully"
    else
        echo "❌ Failed to install some hyprland packages"
        exit 1
    fi

    # Disable mako systemd service - hyprland will start it directly
    echo "   Disabling mako systemd service (hyprland will manage it)"
    systemctl --user disable mako.service 2>/dev/null || true
    systemctl --user stop mako.service 2>/dev/null || true

    # Store WM choice for other scripts
    mkdir -p ~/.local/state/omarchy
    echo "hyprland" > ~/.local/state/omarchy/current-wm

else
    echo "❌ Unknown window manager: $OMARCHY_WM"
    echo "   Supported options: hyprland, niri"
    exit 1
fi

# Common Wayland packages needed by both window managers
COMMON_WAYLAND_PACKAGES=(
    "polkit-gnome"
    "gnome-keyring"
    "pamixer"
    "playerctl"
    "brightnessctl"
    "wireplumber"
    "python-gobject"
)

echo "📦 Installing common Wayland packages..."
if sudo pacman -S --noconfirm --needed "${COMMON_WAYLAND_PACKAGES[@]}"; then
    echo "✅ Common Wayland packages installed successfully"
else
    echo "⚠️  Some common packages failed to install, but continuing..."
fi

echo "✨ Window manager installation completed: $OMARCHY_WM"
