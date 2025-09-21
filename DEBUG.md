# Complete (N)omarchy Installation Workflow

## Phase 1: Boot Script (`boot.sh`)

1. **Display ASCII art** and clear screen
2. **Install prerequisites**: `sudo pacman -Syu --noconfirm --needed git gum`
3. **Setup repository**: 
   - Remove existing `~/.local/share/omarchy`
   - Create symlink from `/mnt/nomarchy` to `~/.local/share/omarchy`
4. **User prompts**:
   - **Interactive mode**: Ask if user wants interactive package selection
   - **Window manager**: Choose between Hyprland and Niri
5. **Set environment variables**:
   - `OMARCHY_INTERACTIVE` (true/false)
   - `OMARCHY_WM` (hyprland/niri)
6. **Launch main installer**: `source ~/.local/share/omarchy/install.sh`

## Phase 2: Main Installation (`install.sh`)

### A. Preparation (`preflight/`)
7. **show-env.sh**: Display environment variables
8. **trap-errors.sh**: Set up error handling
9. **guard.sh**: Check installation prerequisites
10. **chroot.sh**: Check if running in chroot environment
11. **session-manager-detection.sh**: Detect existing DMs (GDM/SDDM/etc) → sets standalone vs overlay mode
12. **pacman.sh**: Configure pacman settings
13. **migrations.sh**: Run any database/config migrations
14. **first-run-mode.sh**: Determine if this is first installation

### B. Package Installation (`packaging/`)
15. **interactive-checkbox.sh**: 
    - Source `packages.sh` to get package list
    - If Niri selected, add `niri` and `grim` packages
    - If interactive mode: show `gum` checkbox interface
    - Install packages (your modified version tries pacman → fallback to yay)
16. **window-manager.sh**: Install window manager specific packages
17. **fonts.sh**: Install fonts
18. **lazyvim.sh**: Setup LazyVim configuration
19. **webapps.sh**: Install web applications
20. **tuis.sh**: Install terminal UI applications

### C. Configuration (`config/`)
21. **config.sh**: Copy base configurations
22. **theme.sh**: Setup themes
23. **branding.sh**: Apply branding
24. **git.sh**: Configure git
25. **gpg.sh**: Setup GPG
26. **timezones.sh**: Configure timezone
27. **increase-sudo-tries.sh**: Increase sudo attempt limit
28. **increase-lockout-limit.sh**: Configure lockout settings
29. **ssh-flakiness.sh**: Fix SSH issues
30. **detect-keyboard-layout.sh**: Auto-detect keyboard layout
31. **xcompose.sh**: Setup compose key
32. **mise-ruby.sh**: Install Ruby via mise
33. **docker.sh**: Configure Docker
34. **niri.sh**: Configure Niri (if selected)
35. **mimetypes.sh**: Setup MIME types
36. **localdb.sh**: Setup local databases
37. **sudoless-asdcontrol.sh**: Configure ASD control

### D. Hardware Configuration (`config/hardware/`)
38. **network.sh**: Configure networking
39. **fix-fkeys.sh**: Fix function keys
40. **bluetooth.sh**: Setup Bluetooth
41. **printer.sh**: Configure printing
42. **usb-autosuspend.sh**: Configure USB power management
43. **ignore-power-button.sh**: Configure power button behavior
44. **nvidia.sh**: Configure NVIDIA drivers (if applicable)
45. **fix-f13-amd-audio-input.sh**: Fix AMD audio input on F13

### E. Login Setup (`login/`)
46. **plymouth.sh**: Setup Plymouth boot screen (only in standalone mode)
47. **desktop-entries.sh**: Create desktop entries for DMs
48. **limine-snapper.sh**: Configure Limine bootloader snapshots
49. **alt-bootloaders.sh**: Configure alternative bootloaders

### F. Finishing (`finishing/`)
50. **reboot.sh**: Prompt for reboot

---

# Manual Step-by-Step Debugging

To debug manually, you can run each phase individually:

## Set Environment Variables First:
```bash
cd /home/dizzyc/Workspace/Personal/nomarchy
export OMARCHY_PATH="$HOME/.local/share/omarchy"
export OMARCHY_INSTALL="$OMARCHY_PATH/install"
export PATH="$OMARCHY_PATH/bin:$PATH"

# Your choices
export OMARCHY_INTERACTIVE=true  # or false
export OMARCHY_WM=niri          # or hyprland
```
## Run Individual Phases:
```bash
# Phase A: Preflight
source $OMARCHY_INSTALL/preflight/show-env.sh
source $OMARCHY_INSTALL/preflight/trap-errors.sh
source $OMARCHY_INSTALL/preflight/guard.sh
source $OMARCHY_INSTALL/preflight/chroot.sh
source $OMARCHY_INSTALL/preflight/session-manager-detection.sh
source $OMARCHY_INSTALL/preflight/pacman.sh
source $OMARCHY_INSTALL/preflight/migrations.sh
source $OMARCHY_INSTALL/preflight/first-run-mode.sh

# Phase B: Packaging (your current issue is here)
source $OMARCHY_INSTALL/packaging/interactive-checkbox.sh
# ... continue with others if needed
```
## Most Relevant for Your Issue:
Since your issue is with package installation, focus on:

```bash
# Debug the package installation specifically
source $OMARCHY_INSTALL/packages.sh
echo "Package list: $OMARCHY_PACKAGES"

# Run the interactive checkbox manually
source $OMARCHY_INSTALL/packaging/interactive-checkbox.sh
```
This gives you the complete picture of what happens when you run `boot.sh` and where exactly your package installation issue occurs (step 15 in the workflow).