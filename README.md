# Arch Linux Automated Install

This script automates the installation of a minimal Arch Linux base system, preparing it to be configured by this [Ansible playbook](https://github.com/henningmyhrvold/dotfiles-playbook).

Last tested Arch Linux ISO: archlinux-2025.08.01-x86_64.iso

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
    * `pacman_packages.txt`: No changes needed, but it is possible to add or remove packages for the base install.
    * `post_install.sh`: No changes needed, this script runs at the end of the installation.
    * `install.py`: You could change default user name in the script but it is not required. Change timezone.

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
5.  **Change myuser name with youruser name**
    ```bash
    git grep -l myuser | xargs sed -i 's/myuser/youruser/g'
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
