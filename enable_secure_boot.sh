#!/bin/bash

set -e  # Exit on error for robustness

efivars_dir="/sys/firmware/efi/efivars"

# Function to make Secure Boot-related EFI variables writable if immutable
make_writable() {
    local patterns=("PK-*" "KEK-*" "db-*" "dbx-*")
    for pattern in "${patterns[@]}"; do
        for file in "$efivars_dir/$pattern"; do
            if [ -f "$file" ]; then
                if lsattr "$file" | grep -q '----i'; then
                    echo "Making $file writable..."
                    sudo chattr -i "$file"
                else
                    echo "$file is already writable."
                fi
            fi
        done
    done
}

# Install required software
sudo pacman -S --needed sbctl

# Create keys if not already installed
if ! sbctl status | grep -q "Installed"; then
    echo "Creating Secure Boot keys..."
    sudo sbctl create-keys
fi

# Attempt to enroll keys, make variables writable if necessary, and retry
echo "Enrolling keys (including Microsoft keys)..."
if ! sudo sbctl enroll-keys -m; then
    echo "Initial enrollment failed. Attempting to make EFI variables writable..."
    make_writable
    if ! sudo sbctl enroll-keys -m; then
        echo "Enrollment failed even after making variables writable. Manual intervention may be required: reboot into your BIOS/UEFI firmware setup (e.g., via 'systemctl reboot --firmware-setup') and set Secure Boot to Setup Mode, then rerun this script."
        exit 1
    fi
fi

# Verify and sign files automatically
echo "Verifying and signing files..."
sudo sbctl verify | sed 's/✗ /sudo sbctl sign -s /e'

# Display final status
sudo sbctl status

echo "Script completed. Reboot your system and verify Secure Boot status in your BIOS/UEFI if necessary. You may need to rerun this script after reboot to confirm everything is signed and enabled."
