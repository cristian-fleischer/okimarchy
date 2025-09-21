#!/bin/bash

# Copy over Omarchy configs
mkdir -p ~/.config
cp -R ~/.local/share/omarchy/config/* ~/.config/

# Use default bashrc from Omarchy
cp ~/.local/share/omarchy/default/bashrc ~/.bashrc

# Copy desktop files for UWSM integration
mkdir -p ~/.local/share/applications
cp -R ~/.local/share/omarchy/applications/* ~/.local/share/applications/ 2>/dev/null || true
