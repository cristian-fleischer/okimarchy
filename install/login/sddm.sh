sudo mkdir -p /etc/sddm.conf.d

# Decide which session to use based on selected WM(s)
session="hyprland-uwsm"
if echo "${OKIMARCHY_WM_SELECTION:-}" | grep -q "Niri"; then
  session="niri-uwsm"
fi

# Ensure Niri (uwsm) session entry exists
sudo mkdir -p /usr/share/wayland-sessions
if [ ! -f /usr/share/wayland-sessions/niri-uwsm.desktop ]; then
  sudo tee /usr/share/wayland-sessions/niri-uwsm.desktop >/dev/null <<'DESKTOP'
[Desktop Entry]
Name=Niri (uwsm)
Comment=Start Niri via UWSM
Exec=uwsm start -- niri --session
Type=Application
DesktopNames=niri
DESKTOP
fi

# Configure SDDM to use the chosen session (create once)
if [ ! -f /etc/sddm.conf.d/autologin.conf ]; then
  cat <<EOF2 | sudo tee /etc/sddm.conf.d/autologin.conf
[Autologin]
User=$USER
Session=$session

[Theme]
Current=breeze
EOF2
fi

# Enable SDDM (no --now to avoid issues during manual installs)
sudo systemctl enable sddm.service
