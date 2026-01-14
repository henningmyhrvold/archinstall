#!/bin/bash
set -euo pipefail

echo "Warning! Secure boot must be activated before continuing"
sudo pacman -S --needed clevis
sleep 2
read -p "Enter the path to the encrypted partition (e.g /dev/nvme0n1p2)" partition_path
clevis luks bind -d $partition_path tpm2 '{}'

echo "Edit /etc/mkinitcpio.conf"
echo 'Add "clevis" to the HOOKS array BEFORE! "encrypt"'
echo "Then regenerate with mkinitcpio -P"
