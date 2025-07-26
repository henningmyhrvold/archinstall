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
    * `install.py`: Change default user name "hm" to your own. If you change the username, change username in the dotfiles and dotfiles-playbook repos.

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
    * cd src/dotfiles-playbook
    * ./bootstrap.sh
    * Wait for the playbook to finish. Reboot.
2.  **Secure Boot**
    * Super + Enter for terminal
    ```bash
    enable_secure_boot.sh
    enable_tpm_autounlock.sh
    ```
