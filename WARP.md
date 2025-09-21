# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Nomarchy (a fork of Omakub) is a comprehensive Linux desktop environment installer that transforms fresh Arch Linux installations into fully-configured, modern web development systems. It supports both Hyprland and Niri window managers with interactive package selection.

## Architecture

### Core Installation Flow

The installation follows a well-defined multi-phase architecture:

1. **Boot Phase** (`boot.sh`): User interaction, environment setup, repository cloning
2. **Main Installation** (`install.sh`): Orchestrates all installation phases
3. **Preflight** (`install/preflight/`): System validation and environment detection
4. **Packaging** (`install/packaging/`): Package installation with interactive selection
5. **Configuration** (`install/config/`): System and application configuration
6. **Login Setup** (`install/login/`): Display manager and boot configuration

### Key Components

- **Modular Scripts**: Each functionality is isolated in individual shell scripts
- **Environment Variables**: Control installation behavior (`OMARCHY_INTERACTIVE`, `OMARCHY_WM`)
- **Package Management**: Supports both pacman and yay with fallback mechanisms
- **Window Manager Support**: Dual support for Hyprland and Niri with 95% keybinding compatibility
- **Installation Modes**: Standalone (auto-login) and Overlay (existing DM integration)

### Script Organization

```
install/
├── preflight/          # System validation and detection
├── packaging/          # Package installation logic
├── config/             # Configuration management
│   └── hardware/       # Hardware-specific configurations
├── login/              # Display manager setup
└── first-run/          # Post-installation tasks
```

## Window Manager Configuration System

### Hyprland Configuration Architecture

Hyprland uses a layered configuration system with clear separation of concerns:

**Base Configuration** (`~/.config/hypr/hyprland.conf`):
- Sources default configs from `~/.local/share/omarchy/default/hypr/`
- Includes theme-specific styling from `~/.config/omarchy/current/theme/hyprland.conf`
- User overrides from individual config files in `~/.config/hypr/`

**User Override Files**:
- `monitors.conf`: Display configuration
- `input.conf`: Keyboard, mouse, touchpad settings
- `bindings.conf`: Custom keybindings
- `envs.conf`: Environment variables
- `autostart.conf`: Startup applications

### Niri Configuration Architecture

Niri uses a template-based configuration generation system that merges defaults with user overrides:

**Main Configuration** (`~/.config/niri/config.kdl`):
- Auto-generated file combining base config with user customizations
- Should not be edited directly

**User Override Files**:
- `monitors.kdl`: Display/output configuration
- `input.kdl`: Keyboard, mouse, touchpad settings
- `layout.kdl`: Gaps, borders, column widths, focus ring styling
- `bindings.kdl`: Custom keybindings

**Configuration Generation Process**:
```bash
omarchy-niri-config-generate  # Merges base + user overrides
omarchy-refresh-niri          # Reloads niri with new config
```

### Key Configuration Files

**Hyprland**:
- Main: `~/.config/hypr/hyprland.conf`
- Defaults: `~/.local/share/omarchy/default/hypr/`
- Overrides: `~/.config/hypr/{monitors,input,bindings,envs,autostart}.conf`

**Niri**:
- Main: `~/.config/niri/config.kdl` (auto-generated)
- Defaults: `~/.local/share/omarchy/default/niri/`
- Overrides: `~/.config/niri/{monitors,input,layout,bindings}.kdl`

## Theming System

### Theme Architecture

The theming engine provides cross-window-manager theme compatibility with unified color schemes:

**Theme Location**: `~/.config/omarchy/themes/[theme-name]/`

**Theme Components**:
- `hyprland.conf`: Hyprland-specific colors and styling
- `niri.conf`: Niri-specific colors, focus rings, borders
- `waybar.css`: Status bar styling
- `mako.ini`: Notification styling
- `alacritty.toml`: Terminal colors
- `walker.css`: Application launcher styling
- `swayosd.css`: On-screen display styling
- `neovim.lua`: Editor colorscheme
- `btop.theme`: System monitor colors
- `chromium.theme`: Browser theme color
- `icons.theme`: Icon theme selection

### Available Themes

- **catppuccin**: Soothing pastel theme (default)
- **catppuccin-latte**: Light variant of Catppuccin
- **everforest**: Green-focused natural theme  
- **gruvbox**: Retro groove colors
- **kanagawa**: Japanese-inspired colors
- **matte-black**: Minimalist dark theme
- **nord**: Arctic, north-bluish color palette
- **osaka-jade**: Cyberpunk-inspired theme
- **ristretto**: Coffee-inspired warm theme
- **rose-pine**: All natural pine, faux fur and a bit of soho vibes
- **tokyo-night**: Dark theme inspired by Tokyo's night skyline

### Theme Management Commands

```bash
# Theme switching
omarchy-theme-set <theme-name>        # Apply specific theme
omarchy-theme-next                    # Cycle to next theme
omarchy-theme-list                    # Show available themes
omarchy-theme-current                 # Show current theme

# Background management
omarchy-theme-bg-next                 # Cycle background image
Super + Ctrl + Space                  # Hotkey for next background
Super + Shift + Ctrl + Space          # Theme picker menu

# Theme installation/removal
omarchy-theme-install <theme-name>    # Install new theme
omarchy-theme-remove <theme-name>     # Remove theme
omarchy-theme-update                  # Update all themes
```

### Theme Application Process

When `omarchy-theme-set` is executed:

1. **Symlink Update**: Links `~/.config/omarchy/current/theme` to selected theme
2. **GNOME Settings**: Updates system dark/light mode preference
3. **Icon Theme**: Applies theme-specific icon set
4. **Chromium**: Sets browser theme colors
5. **Application Reloads**: 
   - Alacritty config reload (touch config file)
   - Waybar restart
   - Mako notification daemon reload
   - SwayOSD restart
6. **Window Manager**: 
   - Hyprland: `hyprctl reload`
   - Niri: Copies theme config and reloads via `niri msg action reload-config`
7. **Background**: Sets new wallpaper matching theme

### Creating Custom Themes

1. Copy existing theme: `cp -r ~/.config/omarchy/themes/catppuccin ~/.config/omarchy/themes/my-theme`
2. Edit color files in the new theme directory
3. Apply: `omarchy-theme-set my-theme`

Key color customization files:
- `niri.conf`: Focus ring and border colors
- `hyprland.conf`: Active border colors
- `waybar.css`: Status bar colors and styling
- `mako.ini`: Notification colors

## Common Development Tasks

### Testing Installation

```bash
# Set up environment for manual testing
cd /home/dizzyc/Workspace/Personal/nomarchy
export OMARCHY_PATH="$HOME/.local/share/omarchy"
export OMARCHY_INSTALL="$OMARCHY_PATH/install"
export PATH="$OMARCHY_PATH/bin:$PATH"

# Set installation preferences
export OMARCHY_INTERACTIVE=true
export OMARCHY_WM=niri  # or hyprland

# Test individual phases
source $OMARCHY_INSTALL/preflight/show-env.sh
source $OMARCHY_INSTALL/packaging/interactive-checkbox.sh
```

### Development Workflow

```bash
# Full installation (requires fresh Arch system)
curl -fsSL https://install.omarchy.org | bash

# Or with environment variables
export OMARCHY_INTERACTIVE=true OMARCHY_WM=niri
curl -fsSL https://install.omarchy.org | bash

# Local development testing (symlinks to /mnt/nomarchy)
./boot.sh
```

### Management Commands

The project includes extensive management utilities in `bin/`:

```bash
# Window manager switching
omarchy-wm-switch niri          # Switch to Niri WM
omarchy-wm-switch hyprland      # Switch to Hyprland WM

# System management
omarchy-check-install-mode      # Check current installation mode
omarchy-compare-keybindings     # Compare WM keybinding compatibility
omarchy-refresh-niri           # Reload Niri configuration
omarchy-niri-config-generate   # Generate Niri config with user overrides

# Application utilities
omarchy-app-detect             # Get app-id for focused window
omarchy-menu                   # Launch Omarchy menu
omarchy-font-set <font>        # Change system font

# Configuration management
omarchy-refresh-config         # Reload all configurations
```

### Package Management

The project uses a sophisticated package management system:

- **Base packages**: Defined in `install/packages.sh`
- **Interactive selection**: Users can choose which package groups to install
- **Window manager specific**: Additional packages based on WM choice
- **Fallback system**: Tries pacman first, then yay for AUR packages

### Testing Window Manager Configurations

```bash
# Test niri configuration generation
omarchy-niri-config-generate

# Compare keybinding compatibility between WMs
omarchy-compare-keybindings

# Test niri session (for debugging startup issues)
omarchy-test-niri-session

# Get app-id for window rules
omarchy-app-detect  # Focus window first, then run
```

## Key Environment Variables

- `OMARCHY_INTERACTIVE`: Enable/disable interactive package selection
- `OMARCHY_WM`: Window manager choice (hyprland/niri)  
- `OMARCHY_FORCE_OVERLAY`: Force overlay mode (preserve existing DM)
- `OMARCHY_PATH`: Base installation directory
- `OMARCHY_INSTALL`: Installation scripts directory

## Installation Modes

### Standalone Mode (Default)
- Fresh installations without display managers
- Auto-login directly to desktop
- Plymouth splash screen integration
- Security via disk encryption + screen lock

### Overlay Mode (Auto-detected)
- Preserves existing display managers (GDM, SDDM, etc.)
- Adds Omarchy sessions to login screen
- Maintains existing desktop environment options

## Development Notes

- All scripts use `set -eE` for immediate error exit
- Modular design allows individual phase testing
- Environment detection handles various system configurations
- Package lists are easily maintainable and version-controlled
- Window manager abstraction allows easy addition of new WMs
- The project maintains backward compatibility while adding new features
- Theme system provides unified styling across all applications
- Configuration override pattern allows safe customization without breaking updates

## Debugging

For installation issues, reference `DEBUG.md` which provides step-by-step debugging workflows. The modular architecture allows isolating and testing individual components without full system installation.

Key debugging commands:
- Check environment: `source $OMARCHY_INSTALL/preflight/show-env.sh`
- Test package installation: `source $OMARCHY_INSTALL/packaging/interactive-checkbox.sh`
- Validate WM config: `omarchy-niri-config-generate` or `hyprctl reload`
