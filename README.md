# Arch Linux Automated Install

This script automates the installation of a minimal Arch Linux base system, preparing it to be configured by an Ansible playbook.

## Pre-installation Steps

1.  **Boot into the Arch Linux ISO.**
2.  **Connect to the internet.**
    * For WiFi, use `iwctl`.
    * Ethernet should work automatically.
3.  **Download the installation files:**
    ```bash
    pacman -Sy --noconfirm git
    git clone https://github.com/henningmyhrvold/archinstall /tmp/archinstall
    cd /tmp/archinstall
    ```
4.  **Review and Modify Scripts**
    * `pacman_packages.txt`: Add or remove packages for the base install.
    * `post_install.sh`: This script runs at the end of the installation.
    * `install.py`: This script requires a disk size greater than 21 GB.

5.  **Extended WiFi commands**
    ```bash
    iwctl
    [iwd]# device list
    [iwd]# station wlan0 scan
    [iwd]# station wlan0 get-networks
    [iwd]# station wlan0 connect "MyWiFi"
    (Enter passphrase: mysecretpassword)
    [iwd]# exit
    ip a
    ping github.com
    ```

## Installation

Run the main installation script. The script will guide you through disk partitioning, user creation, and setting passwords.

```bash
python install.py
```

## Post-Installation
1. **Start Terminal**
    * Log in 
    * Type Hyprland
    * Press Super + Enter to open terminal.
2.  **Secure Boot**
    ```bash
    enable_secure_boot.sh
    enable_tpm_autounlock.sh
    ```
