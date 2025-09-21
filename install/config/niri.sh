#!/bin/bash

# Install niri configuration if niri is selected as window manager
if [[ "$OMARCHY_WM" == "niri" ]]; then
    echo "⚙️  Setting up niri configuration..."
    
    # Create niri config directory
    mkdir -p ~/.config/niri
    
    # Copy user override templates (empty by default)
    echo "📋 Installing user override templates..."
    cp ~/.local/share/omarchy/config/niri/monitors.kdl ~/.config/niri/ 2>/dev/null
    cp ~/.local/share/omarchy/config/niri/input.kdl ~/.config/niri/ 2>/dev/null
    cp ~/.local/share/omarchy/config/niri/layout.kdl ~/.config/niri/ 2>/dev/null
    cp ~/.local/share/omarchy/config/niri/bindings.kdl ~/.config/niri/ 2>/dev/null
    
    # Generate the final configuration using the config generator
    echo "🔧 Generating niri configuration with defaults and overrides..."
    if omarchy-niri-config-generate; then
        echo "✅ Niri configuration generated successfully"
    else
        echo "⚠️  Failed to generate niri configuration, falling back to simple copy..."
        # Fallback: just copy the basic config
        if [[ -f ~/.local/share/omarchy/config/niri/config.kdl ]]; then
            cp ~/.local/share/omarchy/config/niri/config.kdl ~/.config/niri/
        fi
    fi
    
    echo "🎯 Niri configuration setup completed"
    echo "💡 Customize by editing files in ~/.config/niri/"
else
    echo "⏭️  Skipping niri configuration (not selected)"
fi
