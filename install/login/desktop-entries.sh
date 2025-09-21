#!/bin/bash

# Install desktop entries for overlay mode
# These allow Hyprland/Niri to be selected in display managers

if [[ "$OMARCHY_INSTALL_MODE" != "overlay" ]]; then
    echo "⏭️  Not in overlay mode - skipping desktop entry installation"
    return 0
fi

echo "📱 Installing desktop entries for display manager integration..."

# Create omarchy-specific wayland session directory if needed
sudo mkdir -p /usr/share/wayland-sessions/

# Install Hyprland UWSM session for better integration
if [[ "$OMARCHY_WM" == "hyprland" ]] || [[ -z "$OMARCHY_WM" ]]; then
    echo "📋 Installing Hyprland (Omarchy) session..."
    
    sudo tee /usr/share/wayland-sessions/hyprland-omarchy.desktop >/dev/null <<'EOF'
[Desktop Entry]
Name=Hyprland (Omarchy)
Comment=Hyprland with Omarchy configuration
Exec=uwsm start -- hyprland.desktop
TryExec=uwsm
DesktopNames=Hyprland
Type=Application
Keywords=tiling;wayland;compositor;omarchy;
EOF
fi

# Install Niri session for display managers  
if [[ "$OMARCHY_WM" == "niri" ]]; then
    echo "📋 Installing Niri (Omarchy) session..."
    
    sudo tee /usr/share/wayland-sessions/niri-omarchy.desktop >/dev/null <<'EOF'
[Desktop Entry]
Name=Niri (Omarchy)
Comment=Niri scrollable tiling with Omarchy configuration
Exec=uwsm start -- niri.desktop
TryExec=uwsm
DesktopNames=niri
Type=Application
Keywords=scrollable;tiling;wayland;compositor;omarchy;walker;
EOF
fi

# Also create X11 sessions for legacy display managers
echo "🖥️  Installing X11 compatibility sessions..."

sudo mkdir -p /usr/share/xsessions/

# X11 compatibility note session (warns users to use Wayland)
sudo tee /usr/share/xsessions/omarchy-wayland-note.desktop >/dev/null <<'EOF'
[Desktop Entry]
Name=Omarchy (Wayland Required)
Comment=Omarchy requires Wayland - please select Wayland sessions
Exec=sh -c 'zenity --info --text="Omarchy requires Wayland.\n\nPlease log out and select a Wayland session:\n• Hyprland (Omarchy)\n• Niri (Omarchy)" || notify-send "Omarchy" "Please use Wayland sessions for Omarchy"'
Type=Application
Keywords=omarchy;wayland;
EOF

# Set appropriate permissions
sudo chmod 644 /usr/share/wayland-sessions/hyprland-omarchy.desktop 2>/dev/null
sudo chmod 644 /usr/share/wayland-sessions/niri-omarchy.desktop 2>/dev/null  
sudo chmod 644 /usr/share/xsessions/omarchy-wayland-note.desktop 2>/dev/null

echo "✅ Desktop entries installed for overlay mode"
echo "💡 You can now select 'Hyprland (Omarchy)' or 'Niri (Omarchy)' from your display manager"

if [[ -n "$OMARCHY_DM_TYPE" ]]; then
    case "$OMARCHY_DM_TYPE" in
        "gdm")
            echo "🎯 GDM: Click the gear icon to see session options"
            ;;
        "sddm") 
            echo "🎯 SDDM: Use the session dropdown in the bottom-left"
            ;;
        "lightdm")
            echo "🎯 LightDM: Look for session selection in your greeter"
            ;;
        *)
            echo "🎯 Look for session selection options in your display manager"
            ;;
    esac
fi
