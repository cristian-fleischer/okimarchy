# Okimarchy

## Update

Compatibility: Okimarchy is now compatible with Omarchy 3.  
Last synced version: Omarchy 3.1.7

**Okimarchy** is an *okimari* flavor of arch forked from Omarchy.
This transforms Omarchy from an *omakase* (chef's choice) to an *okimari* (pre-set menu) approach:
- **Omakase**: Trust the chef completely (original Omarchy with Hyprland only)
- **Okimari**: Choose from carefully curated options (Okimarchy with Hyprland or Niri)

## Key Features

- **Dual Window Manager Support**: Users can now choose between Hyprland and Niri during installation. Both WMs can be installed simultaneously.
- **Runtime Switching**: Switch between window managers after installation via the Omarchy Menu (*Omarchy Menu (Mod+Alt+Space) -> Setup -> Window Manager*) or `okimarchy-wm-switch` command
- **Consistent Theming**: Niri configurations for all existing themes (Catppuccin, Gruvbox, Nord, Tokyo Night, etc.)
- **Unified Keybindings**: Niri configured to match Hyprland's keybindings and behavior
- Niri is configured to look and feel similar to Hyprland and to follow the Omarchy philosophy.

**Configuration System:**
- Modular Niri configuration files (`bindings.kdl`, `layout.kdl`, `windows.kdl`, etc.) and a dynamic Niri configuration generator (`omarchy-niri-config-gen`)
- Theme-specific Niri configurations for all existing themes

## Installation

1. Download and install arch linux (https://archlinux.org/download/)  
   *Recommended*: Boot from the Arch Linux ISO and run `archinstall`.
2. Install Omarchy by running the following command:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/basecamp/omarchy/master/boot.sh | OMARCHY_REPO="cristian-fleischer/okimarchy" bash
   ```
### Installing on arch derivatives
If you want to install Okimarchy / Omarchy on Cachy OS please have a look at: https://github.com/mroboff/omarchy-on-cachyos
For other derivatives or distros please see: https://learn.omacom.io/2/the-omarchy-manual/79/omarchy-on

---

# Omarchy

Omarchy is a beautiful, modern & opinionated Linux distribution by DHH.

Read more at [omarchy.org](https://omarchy.org).

## License

Omarchy is released under the [MIT License](https://opensource.org/licenses/MIT).
