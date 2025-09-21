#!/bin/bash

# Interactive package installation - sources package list from packages.sh
# Simple implementation: all packages in one list, pre-selected for easy maintenance

# Source the package list from packages.sh
source $OMARCHY_INSTALL/packages.sh

if [[ "$OMARCHY_INTERACTIVE" == "true" ]]; then
    echo "🔍 Interactive package selection enabled"
    echo "   All packages are pre-selected - uncheck what you don't want"
    echo "   Use Space to toggle, Enter to confirm selection"
    echo

    # Convert package string to array - handle backslash-continuation format
    ALL_PACKAGES=()
    # Use eval to properly parse the backslash-continued string into an array
    eval "ALL_PACKAGES=($OMARCHY_PACKAGES)"

    # Add niri package if niri is selected (only package not already in the list)
    if [[ "$OMARCHY_WM" == "niri" ]]; then
        echo "➕ Adding niri package for niri window manager..."
        ALL_PACKAGES+=("niri" "grim")
    fi

    # Create comma-separated list for pre-selection (all packages selected by default)
    pre_selected=""
    printf -v pre_selected '%s,' "${ALL_PACKAGES[@]}"
    pre_selected=${pre_selected%,}  # Remove trailing comma

    echo "📦 Select packages to install ($(echo "${ALL_PACKAGES[@]}" | wc -w) total):"

    # Show interactive selection with all packages pre-selected
    SELECTED_PACKAGES=$(printf '%s\n' "${ALL_PACKAGES[@]}" | sort | gum choose --no-limit --selected="$pre_selected" --height 20)

    if [[ -n "$SELECTED_PACKAGES" ]]; then
        SELECTED_COUNT=$(echo "$SELECTED_PACKAGES" | wc -l)
        echo "✅ Selected $SELECTED_COUNT packages for installation"
        echo
        echo "🚀 Installing selected packages..."
        echo "   This may take a while..."

        # Install selected packages
        # Try pacman first for official packages, then yay for any that failed
        PACKAGE_LIST=$(echo "$SELECTED_PACKAGES" | tr '\n' ' ')
        echo "📦 Attempting installation with pacman first..."
        
        if sudo pacman -S --noconfirm --needed $PACKAGE_LIST; then
            echo "✅ All packages installed successfully with pacman!"
        else
            echo "⚠️  Some packages failed with pacman, trying yay for AUR packages..."
            if yay -S --noconfirm --needed $PACKAGE_LIST; then
                echo "✅ Package installation completed with yay!"
            else
                echo "❌ Some packages failed to install even with yay. Please check the output above."
                exit 1
            fi
        fi
    else
        echo "⚠️  No packages selected, skipping package installation"
        if gum confirm "Continue with installation anyway?"; then
            echo "⏭️  Continuing without packages..."
        else
            echo "❌ Installation cancelled by user"
            exit 1
        fi
    fi

else
    echo "📦 Using automatic package installation..."
    # Automatic installation - install all packages from OMARCHY_PACKAGES
    # Use eval to properly handle backslash-continued format
    eval "PACKAGE_ARRAY=($OMARCHY_PACKAGES)"
    PACKAGE_COUNT=${#PACKAGE_ARRAY[@]}
    
    # Keep as array - don't convert to single string
    INSTALL_PACKAGES=("${PACKAGE_ARRAY[@]}")
    if [[ "$OMARCHY_WM" == "niri" ]]; then
        echo "➕ Including niri package..."
        INSTALL_PACKAGES+=("niri" "grim")
        PACKAGE_COUNT=$((PACKAGE_COUNT + 2))
    fi

    echo "   Installing $PACKAGE_COUNT packages..."

    # Try pacman first, fallback to yay if needed
    echo "📦 Attempting installation with pacman first..."
    if sudo pacman -S --noconfirm --needed "${INSTALL_PACKAGES[@]}"; then
        echo "✅ All packages installed successfully with pacman!"
    else
        echo "⚠️  Some packages failed with pacman, trying yay for AUR packages..."
        if yay -S --noconfirm --needed "${INSTALL_PACKAGES[@]}"; then
            echo "✅ Package installation completed with yay!"
        else
            echo "❌ Some packages failed to install even with yay. Please check the output above."
            exit 1
        fi
    fi
fi
