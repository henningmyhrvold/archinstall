#!/bin/bash
set -euo pipefail

# Exit if not run as root
if [ "$EUID" -ne 0 ]; then
    tput setaf 1
    echo "This script must be run as root."
    tput sgr0
    exit 1
fi

# Function to print colored status updates
print_update() {
    tput setaf 2
    echo "### $1"
    tput sgr0
}

# Check for username argument
if [ -z "${1:-}" ]; then
    tput setaf 1
    echo "Error: Username argument is required."
    tput sgr0
    exit 1
fi

# --- Configuration ---
USERNAME=$1
CONFIG_DIR="/opt/archinstall"
USER_HOME="/home/$USERNAME"
ANSIBLE_REPO_URL="https://github.com/henningmyhrvold/dotfiles-playbook.git"
ARCHINSTALL_REPO_URL="https://github.com/henningmyhrvold/archinstall.git"
# Define the source directory path
SRC_DIR="$USER_HOME/src"
# Define the final destination for the repository, inside the src folder
DOTFILES_DIR="$SRC_DIR/dotfiles-playbook"
ARCHINSTALL_DIR="$SRC_DIR/archinstall"


# --- Pacman Configuration ---
print_update "Configuring pacman..."
sed -i '/^#Color/s/^#//' /etc/pacman.conf
sed -i '/^#ParallelDownloads/s/^#//' /etc/pacman.conf
pacman -Sy --noconfirm

# --- Install Packages ---
print_update "Installing packages from pacman_packages.txt..."
grep -v '^#\|^$' "$CONFIG_DIR/pacman_packages.txt" | pacman -S --noconfirm --needed -

# --- Configure NetworkManager to use iwd ---
print_update "Configuring NetworkManager to use iwd backend..."
mkdir -p /etc/NetworkManager/conf.d
cat <<EOF > /etc/NetworkManager/conf.d/wifi_backend.conf
[device]
wifi.backend=iwd
EOF

# --- Create Source Directory ---
print_update "Creating source directory at $SRC_DIR..."
# Run mkdir as the new user to ensure correct permissions
sudo -u "$USERNAME" mkdir -p "$SRC_DIR"

# --- Clone Ansible Repository ---
print_update "Cloning Ansible playbook into $DOTFILES_DIR..."
# Run git clone as the new user
sudo -u "$USERNAME" git clone "$ANSIBLE_REPO_URL" "$DOTFILES_DIR"
sudo -u "$USERNAME" git clone "$ARCHINSTALL_REPO_URL" "$ARCHINSTALL_DIR"

# This chown is technically redundant because of `sudo -u`, but it's a harmless safety check.
chown -R "$USERNAME":"$USERNAME" "$DOTFILES_DIR"
chmod +x "$DOTFILES_DIR/bootstrap.sh"
print_update "Ansible repository cloned to $DOTFILES_DIR"


# --- Final Message ---
echo
print_update "Installation is complete!"
echo "You can now reboot the system."
echo "After rebooting, log in, start Hyprland, and your Ansible playbook will be ready in '$DOTFILES_DIR'."
echo
