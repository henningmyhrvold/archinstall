#!/bin/bash

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
if [ -z "$1" ]; then
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
# Define the source directory path
SRC_DIR="$USER_HOME/src"
# Define the final destination for the repository, inside the src folder
DOTFILES_DIR="$SRC_DIR/dotfiles-playbook"


# --- Pacman Configuration ---
[cite_start]print_update "Configuring pacman..." [cite: 1]
[cite_start]sed -i '/^#Color/s/^#//' /etc/pacman.conf [cite: 1]
[cite_start]sed -i '/^#ParallelDownloads/s/^#//' /etc/pacman.conf [cite: 1]
[cite_start]pacman -Sy --noconfirm [cite: 1]

# --- Install Packages ---
[cite_start]print_update "Installing packages from pacman_packages.txt..." [cite: 1]
[cite_start]grep -v '^#\|^$' "$CONFIG_DIR/pacman_packages.txt" | pacman -S --noconfirm --needed - [cite: 1]

# --- Configure NetworkManager to use iwd ---
print_update "Configuring NetworkManager to use iwd backend..."
mkdir -p /etc/NetworkManager/conf.d
cat <<EOF > /etc/NetworkManager/conf.d/wifi_backend.conf
[device]
wifi.backend=iwd
EOF

# --- Create Source Directory ---
[cite_start]print_update "Creating source directory at $SRC_DIR..." [cite: 1]
# Run mkdir as the new user to ensure correct permissions
[cite_start]sudo -u "$USERNAME" mkdir -p "$SRC_DIR" [cite: 1]

# --- Clone Ansible Repository ---
[cite_start]print_update "Cloning Ansible playbook into $DOTFILES_DIR..." [cite: 1]
# Run git clone as the new user
[cite_start]sudo -u "$USERNAME" git clone "$ANSIBLE_REPO_URL" "$DOTFILES_DIR" [cite: 1]

if [ $? -ne 0 ]; then
    tput setaf 1
    echo "Error: Failed to clone Ansible repository."
    tput sgr0
else
    # This chown is technically redundant because of `sudo -u`, but it's a harmless safety check.
    [cite_start]chown -R "$USERNAME":"$USERNAME" "$DOTFILES_DIR" [cite: 1]
    [cite_start]print_update "Ansible repository cloned to $DOTFILES_DIR" [cite: 1]
fi


# --- Final Message ---
echo
[cite_start]print_update "Installation is complete!" [cite: 1]
[cite_start]echo "You can now reboot the system." [cite: 1]
[cite_start]echo "After rebooting, log in, start Hyprland, and your Ansible playbook will be ready in '$DOTFILES_DIR'." [cite: 1]
echo
