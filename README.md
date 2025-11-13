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
- Integration with the Omarchy theming system - Theme-specific Niri configurations for all existing themes

Please note there are still open tasks: [To Do](#to-do)

## Installation

1. Download and install arch linux (https://archlinux.org/download/)  
   *Recommended*: Boot from the Arch Linux ISO and run `archinstall`. If needed see [manual installation details](#manual-installation-details).  
3. Install Okimarchy by running the following command:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/basecamp/omarchy/master/boot.sh | OMARCHY_REPO="cristian-fleischer/okimarchy" bash
   ```
### Installing on arch derivatives
If you want to install Okimarchy / Omarchy on Cachy OS please have a look at: https://github.com/mroboff/omarchy-on-cachyos
For other derivatives or distros please see: https://learn.omacom.io/2/the-omarchy-manual/79/omarchy-on


### Manual Installation Details

You can do a manual installation using the vanilla arch ISO, archinstall.

* Download the Arch Linux ISO (https://archlinux.org/download/)
* Write it on a USB stick (use balenaEtcher on Mac/Windows)
* Boot off the stick (remember to turn off Secure Boot in the BIOS!).
* If you're on wifi, start by running iwctl, then type station wlan0 scan, then station wlan0 connect <tab>, pick your network, and enter the password.   
  If you're on ethernet, you don't need this.
* Run archinstall and pick your options

| Section                           | Configuration Option                                                                                        |
|-----------------------------------|-------------------------------------------------------------------------------------------------------------|
| Mirrors and repositories          | Select regions → Your country                                                                               |
| Disk configuration                | **Option 1:** Use entire disk → **Warning: This will erase all data on the disk** <br> **Option 2:** Use existing partition → **Warning: This will overwrite the selected partition** (select with space + return) |
| Disk → File system                | btrfs (default structure: yes + use compression)                                                            |
| Disk → Disk encryption            | (optional but highly recommended) Encryption type: LUKS + Encryption password + Partitions (select the one) |
| Hostname                          | Give your computer a name                                                                                   |
| Bootloader                        | Limine                                                                                                      |
| Authentication → Root password    | Set yours                                                                                                   |
| Authentication → User account     | Add a user → Superuser: Yes → Confirm and exit                                                              |
| Applications → Audio              | pipewire                                                                                                    |
| Network configuration             | Copy ISO network config                                                                                     |
| Timezone                          | Set yours                                                                                                   |


Once Arch has been installed:
 * Reboot
 * login with the user you just setup
 * install Okimarchy  
   `curl -fsSL https://raw.githubusercontent.com/basecamp/omarchy/master/boot.sh | OMARCHY_REPO="cristian-fleischer/okimarchy" bash`

It will run for 5-30 minutes, depending on the speed of your internet connection, please be patient.  
When it's all done, it'll ask for your permission to reboot the system.

## To Do
- [x] Update installation scripts to support selecting WM
- [x] In install split out packages for hyprland and niri so they can be installed independently
- [x] Omarchy Menu - add script to switch between Niri and Hyprland
- [x] Integrate niri into the omarchy theming engine for consistent theming
- [x] Create a niri configuration generator that is able to generate the main niri config out of multiple config files similar to hyprland
- [ ] Replace the above custom implementation with the native niri implementation when it is deployed: https://yalter.github.io/niri/Configuration%3A-Include.html
- [x] Configure Waybar to work with niri workspace indicator module
- [ ] Update the Omarchy Menu to work with niri (many menu items are specific for hyprland)

---

# Omarchy

Omarchy is a beautiful, modern & opinionated Linux distribution by DHH.

Read more at [omarchy.org](https://omarchy.org).

## License

Omarchy is released under the [MIT License](https://opensource.org/licenses/MIT).
