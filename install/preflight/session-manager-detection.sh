#!/bin/bash

# Detect existing session managers and desktop environments
# Sets environment variables for conditional installation behavior

echo "🔍 Detecting existing session management..."

# Initialize detection flags
export OMARCHY_EXISTING_DM=false
export OMARCHY_EXISTING_DE=false
export OMARCHY_DM_TYPE=""
export OMARCHY_DE_TYPE=""

# Detect Display Managers
detect_display_managers() {
    local found_dm=""
    
    # Check for enabled display manager services
    for dm in gdm sddm lightdm lxdm slim xdm ly; do
        if systemctl is-enabled "$dm.service" >/dev/null 2>&1; then
            found_dm="$dm"
            break
        fi
    done
    
    # Also check for installed but not necessarily enabled DMs
    if [[ -z "$found_dm" ]]; then
        for dm in gdm sddm lightdm lxdm; do
            if command -v "$dm" >/dev/null 2>&1; then
                found_dm="$dm"
                break
            fi
        done
    fi
    
    if [[ -n "$found_dm" ]]; then
        export OMARCHY_EXISTING_DM=true
        export OMARCHY_DM_TYPE="$found_dm"
        echo "✓ Found display manager: $found_dm"
    else
        echo "ℹ️  No display manager detected"
    fi
}

# Detect Desktop Environments
detect_desktop_environments() {
    local found_de=""
    
    # Check for installed desktop environments via package detection
    if pacman -Qi gnome-shell >/dev/null 2>&1; then
        found_de="gnome"
    elif pacman -Qi plasma-desktop >/dev/null 2>&1; then
        found_de="kde"
    elif pacman -Qi xfce4-session >/dev/null 2>&1; then
        found_de="xfce"
    elif pacman -Qi mate-session-manager >/dev/null 2>&1; then
        found_de="mate"
    elif pacman -Qi cinnamon-session >/dev/null 2>&1; then
        found_de="cinnamon"
    elif pacman -Qi lxde-common >/dev/null 2>&1; then
        found_de="lxde"
    elif pacman -Qi lxqt-session >/dev/null 2>&1; then
        found_de="lxqt"
    fi
    
    # Check for tiling window managers
    if [[ -z "$found_de" ]]; then
        for wm in i3 awesome dwm bspwm herbstluftwm qtile; do
            if command -v "$wm" >/dev/null 2>&1; then
                found_de="$wm"
                break
            fi
        done
    fi
    
    if [[ -n "$found_de" ]]; then
        export OMARCHY_EXISTING_DE=true
        export OMARCHY_DE_TYPE="$found_de"
        echo "✓ Found desktop environment/WM: $found_de"
    else
        echo "ℹ️  No existing desktop environment detected"
    fi
}

# Detect current session type
detect_current_session() {
    if [[ -n "$XDG_CURRENT_DESKTOP" ]]; then
        echo "ℹ️  Current session: $XDG_CURRENT_DESKTOP"
    fi
    
    if [[ -n "$XDG_SESSION_TYPE" ]]; then
        echo "ℹ️  Session type: $XDG_SESSION_TYPE"
    fi
}

# Main detection
detect_display_managers
detect_desktop_environments
detect_current_session

# Determine installation mode
if [[ "$OMARCHY_FORCE_OVERLAY" == "true" ]] || [[ "$OMARCHY_EXISTING_DM" == "true" ]]; then
    echo "🎯 Installation mode: Overlay (keeping existing session manager)"
    echo "   - Seamless login will be SKIPPED"
    echo "   - Desktop entries will be created for session manager"
    if [[ -n "$OMARCHY_DM_TYPE" ]]; then
        echo "   - Existing display manager: $OMARCHY_DM_TYPE"
    fi
    if [[ "$OMARCHY_FORCE_OVERLAY" == "true" ]]; then
        echo "   - Forced overlay mode via OMARCHY_FORCE_OVERLAY=true"
    fi
    export OMARCHY_INSTALL_MODE="overlay"
else
    echo "🎯 Installation mode: Standalone (seamless login)"
    echo "   - Seamless auto-login will be configured"
    echo "   - Direct boot to Omarchy desktop"
    export OMARCHY_INSTALL_MODE="standalone"
fi

if [[ "$OMARCHY_EXISTING_DE" == "true" ]]; then
    echo "⚠️  Existing desktop environment detected: $OMARCHY_DE_TYPE"
    echo "   - This may cause conflicts with Omarchy configuration"
    echo "   - Consider backing up existing configs"
fi

echo "✅ Session detection completed"
