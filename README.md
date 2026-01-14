# Arch Linux Automated Install

This script automates the installation of a minimal Arch Linux base system, preparing it to be configured by this [Ansible playbook](https://github.com/henningmyhrvold/dotfiles-playbook).

Last tested Arch Linux ISO: archlinux-2025.09.01-x86_64.iso

## Pre-installation Steps

1.  **Boot into the current Arch Linux ISO.**
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
    * `config.json`: Edit this file to customize hostname, username, timezone, swap size, and mirror addresses.
    * `pacman_packages.txt`: No changes needed, but it is possible to add or remove packages for the base install.
    * `post_install.sh`: No changes needed, this script runs at the end of the installation.
    * `install.py`: No changes needed, configuration is loaded from `config.json`.

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

6.  **Configuration**
    
    Edit `config.json` to customize your installation:
    ```json
    {
        "hostname": "arch",
        "username": "henning",
        "timezone": "Europe/Oslo",
        "swap_size": "8G",
        "pacman_mirror": "192.168.1.100",
        "aur_mirror": "192.168.1.100"
    }
    ```
    
    | Setting | Description |
    |---------|-------------|
    | `hostname` | System hostname |
    | `username` | Default sudo user (prompted during install) |
    | `timezone` | System timezone (e.g., `America/New_York`) |
    | `swap_size` | Size of swap file (e.g., `8G`, `16G`) |
    | `pacman_mirror` | Local pacman mirror IP (only used if local mirrors enabled) |
    | `aur_mirror` | Local AUR mirror IP (only used if local mirrors enabled) |

## Installation

Run the main installation script. The script will guide you through disk partitioning, user creation, and setting passwords.

```bash
python install.py
```

## Post-Installation
1. **Start Terminal**
    * Log in 
    * cd src/dotfiles-playbook
    * ./bootstrap.sh
    * Wait for the playbook to finish. Reboot the machine.
2.  **Enable Secure Boot**
    * Super + Enter for terminal
    ```bash
    enable_secure_boot.sh
    ```
    * Reboot into UEFI/BIOS, turn on secure boot and enable user mode. 
    * Boot into arch. Run script again.
    ```bash
    enable_secure_boot.sh
    ```
    * If you enables user mode correctly it should now give a status with green check marks. 
3.  **Enable TPM autounlock**
    * Super + Enter for terminal
    ```bash
    enable_tpm_autounlock.sh
    ```
