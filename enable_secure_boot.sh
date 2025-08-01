#!/bin/bash

set -e

# Install sbctl if not present
sudo pacman -S --needed sbctl

# Define keys directory
KEYS_DIR="/var/lib/sbctl/keys"

# Get current status
STATUS=$(sudo sbctl status)

# Create keys if they do not exist
if [ ! -d "$KEYS_DIR" ]; then
    sudo sbctl create-keys
fi

# Enroll keys only if not already enrolled (no Owner GUID) and in Setup Mode
if ! echo "$STATUS" | grep -q "Owner GUID:"; then
    if echo "$STATUS" | grep "Setup Mode:" | grep -q "Enabled"; then
        sudo sbctl enroll-keys -m -i
    else
        echo "The system is not in Setup Mode, which is required to enroll keys."
        echo "Reboot into firmware setup using: sudo systemctl reboot --firmware-setup"
        echo "In the UEFI/BIOS settings, clear the existing Secure Boot keys to enter Setup Mode."
        echo "After making the changes, boot back into the system and rerun this script."
        exit 1
    fi
fi

# Sign any unsigned files
sudo sbctl verify | sed 's/✗ /sudo sbctl sign -s /e'

# Refresh and display status
STATUS=$(sudo sbctl status)
echo "$STATUS"

# Instruct to enable Secure Boot if it remains disabled
if echo "$STATUS" | grep "Secure Boot:" | grep -q "Disabled"; then
    echo "Keys have been enrolled and files signed, but Secure Boot is still disabled."
    echo "Reboot into firmware setup using: sudo systemctl reboot --firmware-setup"
    echo "In the UEFI/BIOS settings, enable Secure Boot."
    echo "After rebooting, the system should now boot with Secure Boot enforced."
    echo "Rerun this script afterward to confirm the status or sign any new files if necessary."
else
    echo "Secure Boot setup is complete and enabled."
fi
