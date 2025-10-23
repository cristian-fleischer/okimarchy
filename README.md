# Okimarchy

**Okimarchy** is an *okimari* flavor of arch forked from Omarchy.
**Okimari** usually refers to **pre-set menus or fixed combinations** (like a lunch set, sushi set, or kaiseki-style course).
You’re not leaving everything to the chef (*omakase*). Instead, you’re choosing from a **predefined set** (*okimari*).

In this case you get one choice during installation. You get to choose between Hyprland and Niri as your window manager. You can even install both.
Niri is configured to look and feel similar to Hyprland and to follow the Omarchy philosophy.

You can also switch between Hyprland and Niri as your window manager after installation by going to the *Omarchy Menu (Mod+Alt+Space) -> Setup -> Window Manager*. This will install the necessary packages (if not already installed) and configure the window manager to start as default on boot.
Or you can switch the window manager by running `okimarchy-wm-switch` in the terminal.

## Installation

1. Download and install arch linux (https://archlinux.org/download/)
   *Recommended*: Boot from the Arch Linux ISO and run `archinstall`.
2. Install Omarchy by running the following command:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/cristian-fleischer/okimarchy/master/boot.sh | OMARCHY_REPO="cristian-fleischer/okimarchy" OMARCHY_REF="add-niri-as-wm-option" bash
   ```

---

# Omarchy

Omarchy is a beautiful, modern & opinionated Linux distribution by DHH.

Read more at [omarchy.org](https://omarchy.org).

## License

Omarchy is released under the [MIT License](https://opensource.org/licenses/MIT).
