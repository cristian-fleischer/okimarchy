# Enhanced Omarchy Features

This manual documents the enhanced features added to Omarchy, including interactive package selection and Niri window manager support.

## Installation Modes

Omarchy now supports two installation approaches to accommodate different system setups.

### Interactive Package Selection

When you run the Omarchy installer, you'll be prompted to choose your installation mode:

```
🔧 Installation mode:
Use interactive mode? (Confirm each application group) [y/N]
```

**Interactive mode** presents a comprehensive package selection interface where you can choose exactly which applications to install. The system shows all ~127+ packages in a scrollable list with **all packages pre-selected by default**. You simply uncheck what you don't want using **Space** to toggle and **Enter** to confirm your selection.

The interface uses `gum choose` for a clean, terminal-based selection experience:
- All packages are sorted alphabetically for easy browsing
- Window manager specific packages (like `niri`, `grim`) are automatically added based on your WM choice
- Fallback installation tries `pacman` first, then `yay` for AUR packages

If you prefer the original experience, just press **N** and Omarchy will install all packages automatically like it always has.

### Window Manager Selection

After choosing your installation mode, you'll select your window manager:

```
🪟 Window manager selection:
> Hyprland (default)
  Niri (scrollable tiling)
```

**Hyprland** is the original Omarchy experience — traditional tiling with floating windows and all the features you know.

**Niri** is a modern scrollable-tiling compositor that arranges windows in an infinite horizontal desktop. Think of it like having unlimited columns that you can scroll through, similar to GNOME's PaperWM.

### System Installation Modes

Omarchy automatically detects your system configuration and chooses the appropriate installation method:

**Standalone Mode** (Default)
- For fresh Arch installations or systems without display managers
- Provides seamless auto-login directly to the Omarchy desktop
- No login screen — boots directly from Plymouth splash to desktop
- Relies on disk encryption + screen lock for security

**Overlay Mode** (Auto-detected)
- For existing systems with display managers (GDM, SDDM, LightDM, etc.)
- Preserves your existing session manager
- Adds "Hyprland (Omarchy)" or "Niri (Omarchy)" to your login screen
- Choose when to use Omarchy vs your existing desktop environment

You can force overlay mode on any system using `export OMARCHY_FORCE_OVERLAY=true` before installation.

## Window Managers

### Hyprland

The original Omarchy experience with traditional tiling, floating windows, and all the features you're familiar with.

### Niri

Niri brings a unique scrollable-tiling approach to Omarchy while maintaining **95% keybinding compatibility** with Hyprland.

#### What Makes Niri Different

- **Scrollable columns**: Windows are arranged in columns that you can scroll through horizontally
- **No floating windows**: Everything tiles, but in a more flexible column-based layout
- **Infinite desktop**: Scroll left or right through your window columns without workspace boundaries
- **Same applications**: Uses all the same Omarchy apps (Walker, Waybar, Mako, etc.)

#### Automatic Workspace Assignment

Just like Hyprland, applications automatically open on designated workspaces:
- **Workspace 1**: Browsers (Chromium, Firefox)
- **Workspace 2**: Development (VS Code, Neovim)
- **Workspace 3**: Productivity (Obsidian)
- **Workspace 4**: Communication (Signal, Discord)
- **Workspace 5**: Security (1Password)

#### Keybindings

Niri uses **identical keybindings** to Hyprland for maximum compatibility:

**Applications**
- `Super + Space` → Launch Walker
- `Super + Return` → Terminal
- `Super + F/B/M/N/T/D/G/O` → File manager/Browser/Music/Neovim/Activity/Docker/Signal/Obsidian
- `Super + /` → 1Password

**Window Management**
- `Super + Arrows` → Navigate windows/columns
- `Super + W` → Close window
- `Super + Shift + Arrows` → Move/swap windows
- `Alt + Tab` → Cycle windows
- `Shift + F11` → Fullscreen

**Workspaces**
- `Super + 1-9` → Switch workspaces
- `Super + Shift + 1-9` → Move window to workspace
- `Super + Tab/Shift+Tab` → Next/Previous workspace

**System & Media**
- `Super + Escape` → Power menu
- `Super + Alt + Space` → Omarchy menu
- `Print/Shift+Print` → Screenshots
- All volume/brightness/playback keys work identically

**Niri-Specific Controls**
- `Super + R` → Cycle column widths
- `Super + [` → Consume window into column
- `Super + ]` → Expel window from column

You can see the compatibility between window managers using `omarchy-compare-keybindings`.

## Customization

### Hyprland Customization

Hyprland customization works exactly as documented in the main Omarchy manual:

- **Keybindings**: `~/.config/hypr/bindings.conf`
- **Monitors**: `~/.config/hypr/monitors.conf`
- **Input**: `~/.config/hypr/input.conf`
- **Environment**: `~/.config/hypr/envs.conf`
- **Autostart**: `~/.config/hypr/autostart.conf`

### Niri Customization

Niri follows the same override pattern as Hyprland, with configuration files that let you customize specific aspects without breaking the base setup:

- **Keybindings**: `~/.config/niri/bindings.kdl`
- **Monitors**: `~/.config/niri/monitors.kdl`
- **Input**: `~/.config/niri/input.kdl`
- **Layout**: `~/.config/niri/layout.kdl`

Each file contains helpful examples and comments. After making changes, regenerate your configuration:

```bash
omarchy-niri-config-generate
omarchy-refresh-niri
```

#### Example Customizations

**Custom Keybinding** (`~/.config/niri/bindings.kdl`):
```kdl
binds {
    // Override terminal to always open in home directory
    "Mod+Return" { spawn "alacritty" "--working-directory" "/home/username"; }
    
    // Custom screenshot directory
    "Print" { spawn "grim" "-g" "$(slurp)" "~/Screenshots/$(date +%Y-%m-%d_%H-%M-%S).png"; }
}
```

**Dual Monitor Setup** (`~/.config/niri/monitors.kdl`):
```kdl
output "DP-1" {
    mode "2560x1440@165.000"
    position x=0 y=0
    scale 1.0
}

output "HDMI-A-1" {
    mode "1920x1080@60.000"
    position x=2560 y=0
    scale 1.0
}
```

**Custom Layout** (`~/.config/niri/layout.kdl`):
```kdl
layout {
    gaps 16  // Bigger gaps
    
    focus-ring {
        width 4  // Thicker focus ring
        active-color "#ff0000"
    }
}
```

### Themes

All existing Omarchy themes work with both window managers. The enhanced theme system now provides seamless cross-window-manager compatibility:

**Theme Switching**: 
- `Super + Ctrl + Shift + Space` → Theme picker menu
- `omarchy-theme-set <theme-name>` → Apply specific theme
- `omarchy-theme-next` → Cycle to next theme

**Automatic WM Detection**: The theme system automatically detects which window manager is running and applies the appropriate configurations:
- **Hyprland**: Triggers `hyprctl reload` and applies `hyprland.conf` styling
- **Niri**: Copies `niri.conf` to the runtime theme directory and triggers `niri msg action reload-config`

**Theme Components** (each theme includes):
- `hyprland.conf` → Hyprland-specific colors and borders
- `niri.conf` → Niri-specific focus rings, borders, and layout styling  
- `waybar.css`, `mako.ini`, `alacritty.toml` → Application styling
- `chromium.theme`, `icons.theme` → System integration

## Implementation Enhancements

### Modular Installation Architecture

The installation system has been completely restructured for maintainability and flexibility:

**Package Management**:
- **Merge-Conflict Resistant Format**: Package list uses backslash continuation format (`package \`) identical to upstream for minimal merge conflicts when packages are added/removed
- **Separated Concerns**: Package definitions (`install/packages.sh`), installation logic (`install/packaging/interactive-checkbox.sh`), and window manager specifics (`install/packaging/window-manager.sh`) are now separate
- **Robust Parsing**: Uses `eval` to properly handle backslash-continued package strings into bash arrays
- **Fallback Strategy**: Automatic fallback from `pacman` to `yay` for AUR packages

**Installation Mode Detection**:
- **Automatic Detection**: Scans for existing display managers (GDM, SDDM, LightDM) and desktop environments
- **Overlay vs Standalone**: Automatically chooses overlay mode when existing DMs are found, standalone otherwise  
- **Force Override**: `OMARCHY_FORCE_OVERLAY=true` forces overlay mode on any system
- **Session Integration**: Creates proper `.desktop` files for display manager integration

**Configuration System**:
- **Template-Based Generation**: Niri config is generated by merging base templates with user overrides
- **Override Pattern**: Both Hyprland and Niri use consistent override files (monitors, input, layout, bindings)
- **Live Reloading**: Changes can be applied without logout via `omarchy-refresh-niri`

**Installation Safety**:
- **Fixed Source Issues**: Changed `exit 0` to `return 0` in sourced scripts to prevent installation termination
- **Error Handling**: Proper error trapping and recovery mechanisms
- **Environment Validation**: Comprehensive preflight checks for system compatibility

## Management Tools

### Window Manager Switching

You can switch between window managers after installation:

```bash
# Switch to niri (requires logout/login)
omarchy-wm-switch niri

# Switch back to hyprland
omarchy-wm-switch hyprland

# Check current installation mode
omarchy-check-install-mode
```

### Enhanced Tools

**Cross-WM Management**:
```bash
# Switch between window managers (requires logout)
omarchy-wm-switch niri
omarchy-wm-switch hyprland

# Check current installation mode (overlay vs standalone)
omarchy-check-install-mode

# Compare keybinding compatibility between WMs
omarchy-compare-keybindings
```

**Niri-Specific Tools**:
```bash
# Generate niri config by merging defaults + user overrides
omarchy-niri-config-generate

# Reload niri config after making changes
omarchy-refresh-niri

# Get app-id of focused window (for window rules)
omarchy-app-detect

# Test niri session startup (debugging)
omarchy-test-niri-session
```

**Configuration Workflow**:
1. Edit override files: `~/.config/niri/{monitors,input,layout,bindings}.kdl`
2. Regenerate config: `omarchy-niri-config-generate`
3. Apply changes: `omarchy-refresh-niri`

## Environment Variables

You can customize the installation using environment variables:

```bash
# Enable interactive package selection
export OMARCHY_INTERACTIVE=true

# Use niri instead of hyprland  
export OMARCHY_WM=niri

# Force overlay mode (keep existing display manager)
export OMARCHY_FORCE_OVERLAY=true

# Set custom installation paths (for development)
export OMARCHY_PATH="$HOME/.local/share/omarchy"
export OMARCHY_INSTALL="$OMARCHY_PATH/install"

# Then run the installer
curl -fsSL https://install.omarchy.org | bash
```

**Installation Modes**:
- `OMARCHY_INTERACTIVE=true` → Show package selection interface
- `OMARCHY_INTERACTIVE=false` (or unset) → Install all packages automatically
- `OMARCHY_WM=niri` → Use Niri window manager
- `OMARCHY_WM=hyprland` (or unset) → Use Hyprland window manager
- `OMARCHY_FORCE_OVERLAY=true` → Force overlay mode regardless of system state

## Migration and Compatibility

All enhanced features are **100% backward compatible**:

- Default behavior unchanged (Hyprland + automatic installation)
- Existing configurations continue working
- No breaking changes to existing scripts
- New features are entirely opt-in

### Switching to Niri

If you have an existing Omarchy installation with Hyprland:

1. **Install niri packages**: `sudo pacman -S niri grim xwayland-satellite`
2. **Switch window manager**: `omarchy-wm-switch niri`
3. **Generate niri config**: `omarchy-niri-config-generate`
4. **Log out and back in** (or restart your session)

**Note**: The switch command automatically:
- Updates your window manager state file
- Configures the appropriate session startup
- Preserves all your existing themes and configurations

### Adding Custom Window Rules

1. Focus the app and run: `omarchy-app-detect`
2. Note the app-id in the output
3. Edit `~/.config/niri/config.kdl` or create `~/.config/niri/window-rules.kdl`
4. Add your rule:
   ```kdl
   window-rule {
       match app-id="your-app-id"
       open-on-workspace 3
   }
   ```
5. Regenerate config: `omarchy-niri-config-generate && omarchy-refresh-niri`

## Development & Debugging

### Enhanced Development Workflow

The installation system now supports comprehensive development and debugging:

**Testing Installation Components**:
```bash
# Set up development environment
cd /path/to/nomarchy
export OMARCHY_PATH="$HOME/.local/share/omarchy"
export OMARCHY_INSTALL="$OMARCHY_PATH/install"
export PATH="$OMARCHY_PATH/bin:$PATH"

# Test individual installation phases
source $OMARCHY_INSTALL/preflight/show-env.sh
source $OMARCHY_INSTALL/packaging/interactive-checkbox.sh
source $OMARCHY_INSTALL/packaging/window-manager.sh
```

**Configuration Testing**:
```bash
# Test niri configuration generation
omarchy-niri-config-generate

# Validate configuration syntax
niri validate ~/.config/niri/config.kdl

# Test session startup without logging out
omarchy-test-niri-session
```

**Package Management Testing**:
```bash
# Test package parsing (without installation)
OMARCHY_INTERACTIVE=true bash -c 'source install/packages.sh && echo "Packages: ${#PACKAGE_ARRAY[@]}"'

# Compare package lists between branches
diff <(git show main:install/packages.sh) install/packages.sh
```

**Debugging Tools**:
- `DEBUG.md` provides step-by-step debugging workflows
- Modular architecture allows testing individual components
- Environment validation catches common issues early
- Comprehensive logging for installation troubleshooting
