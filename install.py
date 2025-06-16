import shutil
import subprocess
from pathlib import Path

import archinstall
from archinstall import SysInfo, debug, info
from archinstall.lib import disk, exceptions, locale, models
from archinstall.lib.disk import select_devices, suggest_single_disk_layout
from archinstall.lib.exceptions import ArchinstallError
from archinstall.lib.global_menu import GlobalMenu
from archinstall.lib.installer import Installer
from archinstall.lib.menu import ask_chroot, yes_no
from archinstall.lib.models import Bootloader, User
from archinstall.lib.models.network_configuration import NetworkConfiguration
from archinstall.lib.storage import run_disk_operations
from archinstall.lib.utils.util import get_password
from archinstall.tui import Alignment, EditMenu, Tui

# --- Globals ---
SUDO_USER = None
CONFIG_DIR = "/opt/archinstall"
ISO_CONFIG_DIR = "/tmp/archinstall"
MOUNT_POINT: Path | str = ""


def ask_user(title="", default_text="") -> str:
    """Helper function to get user input via a TUI menu."""
    return (
        EditMenu(
            title=title,
            allow_skip=False,
            alignment=Alignment.CENTER,
            default_text=default_text,
        )
        .input()
        .text()
    )


def prompt_disk_and_encryption(fs_type="ext4", separate_home=False) -> None:
    """
    Guides the user through disk selection, layout suggestion, and encryption setup.
    """
    block_devices = select_devices()
    
    suggested_layout = suggest_single_disk_layout(
        block_devices[0], models.FileSystemType(fs_type), separate_home=separate_home
    )

    if yes_no("Do you want to enable disk encryption?"):
        encryption_password = get_password("Enter disk encryption password: ")
        
        encryption_config = {
            "encryption_type": "luks",
            "password": encryption_password,
            "partitions": []
        }

        for device_props in suggested_layout.values():
            for partition in device_props.get('partitions', []):
                if partition.get('mountpoint') != Path("/boot"):
                    partition['encrypted'] = True
                    encryption_config["partitions"].append(partition)
        
        archinstall.arguments['--disk-encryption'] = encryption_config

    archinstall.arguments['--disk-config'] = suggested_layout


def parse_user() -> list[User]:
    """Prompts for and creates a sudo user."""
    global SUDO_USER
    SUDO_USER = ask_user("Sudo user username", "user")
    password = get_password(text="Sudo user password")
    return [User(SUDO_USER, password, sudo=True)]


def chroot_cmd(cmd: str) -> None:
    """Executes a command inside the arch-chroot environment."""
    # Ensure MOUNT_POINT is a string for subprocess
    ret = subprocess.run(
        ["arch-chroot", str(MOUNT_POINT), "/bin/bash", "-c", cmd],
        check=False
    )
    if ret.returncode != 0:
        raise ArchinstallError(f"Failed to run chroot command: {cmd}")


def configure_system():
    """Copies configuration files and runs the post-install script."""
    info("Copying configuration files to new system")
    target_config_dir = Path(f"{MOUNT_POINT}{CONFIG_DIR}")
    
    # Ensure the parent directory exists on the target
    target_config_dir.parent.mkdir(parents=True, exist_ok=True)
    
    # Move the entire configuration directory from the ISO into the new system
    shutil.move(ISO_CONFIG_DIR, target_config_dir.parent)

    post_install_script = f"{CONFIG_DIR}/post_install.sh"
    chroot_cmd(f"chmod +x {post_install_script}")
    info("Starting post-install script...")
    chroot_cmd(f"{post_install_script} {SUDO_USER}")


def perform_installation(mountpoint: Path) -> None:
    """
    Performs the main installation steps using the Installer class API.
    """
    info("Starting base system installation...")
    
    # The modern Installer class takes the mountpoint and the entire arguments
    # dictionary, simplifying its creation.
    with Installer(mountpoint, archinstall.arguments) as installation:
        
        # Mounts are handled by run_disk_operations.
        if not installation.is_mounted(str(mountpoint)):
             installation.mount_ordered_layout()

        # Set mirrors for downloading packages
        installation.set_mirrors()

        # Install base system, kernel, and essential packages
        installation.minimal_installation()

        # Install and configure the bootloader
        installation.add_bootloader()

        # Configure network using NetworkManager
        installation.configure_networking()

        # Create users and set passwords
        installation.create_users()
        installation.user_set_pw("root", archinstall.arguments.get("--!root-password"))

        # Configure timezone and time sync
        installation.set_timezone()
        installation.activate_time_synchronization()

        # Enable services
        installation.enable_service()

        # Generate the fstab file
        installation.genfstab()

        # Run custom setup script
        # Do this inside the 'with' block to ensure the system is still mounted.
        configure_system()

        # Offer to chroot into the new system for manual changes
        if not archinstall.arguments.get("--silent"):
            with Tui():
                if ask_chroot():
                    try:
                        installation.drop_to_shell()
                    except Exception as e:
                        info(f"Could not drop to shell: {e}")


def main():
    """Defines configuration and runs the entire installation process."""
    # Set default configurations
    archinstall.arguments.update({
        "--packages": [],  # All packages are handled by post_install.sh
        "--services": ["NetworkManager", "sshd"],
        "--bootloader": Bootloader.SYSTEMD,
        "--hostname": "archlinux",
        "--locale-config": models.LocaleConfiguration('en_US.UTF-8', 'en_US'),
        "--swap": True,
        "--uki": True,
    })

    # Interactive phase: Get user input
    with Tui():
        prompt_disk_and_encryption()
        archinstall.arguments["--!users"] = parse_user()
        archinstall.arguments["--!root-password"] = get_password("Enter root password")
        archinstall.arguments["--hostname"] = ask_user("Enter hostname", archinstall.arguments['--hostname'])

        # Allow user to review and modify all settings before continuing
        GlobalMenu(data_store=archinstall.arguments).run()

    # Save configuration for debugging and re-use
    archinstall.save_config(archinstall.arguments)
    archinstall.save_secure_config(archinstall.arguments)
    
    if archinstall.arguments.get("--dry-run"):
        exit(0)

    if not archinstall.arguments.get("--silent"):
        with Tui():
            if not yes_no("All configuration is set. Do you want to continue with the installation?"):
                debug("Installation aborted by user.")
                return

    # Perform all disk operations (partitioning, formatting, encryption, mounting)
    mounts = run_disk_operations(archinstall.arguments)
    
    global MOUNT_POINT
    # Find the root mountpoint from the list of mounted devices
    MOUNT_POINT = next(mount.mountpoint for mount in mounts if mount.mountpoint == Path('/'))

    # Start the installation on the mounted system
    perform_installation(MOUNT_POINT)
    
    info("Installation complete. You can now reboot.")


if __name__ == "__main__":
    archinstall.set_log_path('/var/log/archinstall')
    main()

