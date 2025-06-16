#!/usr/bin/env python3
import shutil
import subprocess
from pathlib import Path

import archinstall
from archinstall import SysInfo, debug, info
from archinstall.lib import disk, locale, models
from archinstall.lib.interactions.disk_conf import select_devices, suggest_single_disk_layout
from archinstall.tui.menu_item import MenuItemGroup
from archinstall.lib.global_menu import GlobalMenu
from archinstall.lib.installer import Installer
from archinstall.lib.models import Bootloader, User
from archinstall.lib.models.network_configuration import NetworkConfiguration
from archinstall.lib.utils.util import get_password
from archinstall.tui import Tui
from archinstall.tui.types import Alignment
from archinstall.tui.curses_menu import EditMenu

# --- Globals ---
# This remains useful for passing the username to the post-install script.
SUDO_USER: str | None = None
# These paths are constants and are fine as they are.
CONFIG_DIR = "/opt/archinstall"
# It's good practice to ensure this directory exists before trying to move it.
ISO_CONFIG_DIR = Path("/tmp/archinstall")
# The mountpoint is now handled more dynamically by the Installer.
MOUNT_POINT: Path | None = None


def ask_user(title="", default_text="") -> str:
    """Helper function to get user input via a TUI menu. This function is fine."""
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
    This function is updated to use the modern configuration object.
    """
    # ** API CHANGE **
    # We no longer use a global 'Arguments' dictionary.
    # Instead, we get the central configuration object from archinstall.storage.
    config = archinstall.storage.config

    block_devices = select_devices()
    if not block_devices:
        raise RuntimeError("No suitable block devices found for installation.")
    
    # Suggest a layout for the selected device.
    suggested_layout = suggest_single_disk_layout(
        block_devices[0], models.FileSystemType(fs_type), separate_home=separate_home
    )

    if MenuItemGroup.yes_no("Do you want to enable disk encryption?"):
        encryption_password = get_password("Enter disk encryption password: ")
        
        # ** API CHANGE **
        # Instead of creating a separate encryption_config dictionary,
        # we now set the encryption properties directly on each partition object.
        # The installer will automatically detect this and set up LUKS.
        for partition in suggested_layout.partitions:
            # We encrypt all partitions except the boot partition.
            if partition.mountpoint not in [Path("/boot"), Path("/boot/efi")]:
                partition.set_encryption(password=encryption_password)
    
    # ** API CHANGE **
    # We assign the fully configured layout object to the config.
    config.disk_config = suggested_layout
    # We also need to tell the installer where to mount everything.
    # A temporary mountpoint is created by the installer.
    config.mountpoint = '/mnt/archinstall'


def configure_system(installation: Installer):
    """
    Copies configuration files and runs the post-install script.
    This function is updated to use the Installer's chroot method.
    """
    global SUDO_USER, CONFIG_DIR, ISO_CONFIG_DIR
    
    info("Copying configuration files to new system")
    # The installer instance knows its mountpoint.
    mount_point = installation.mountpoint
    target_config_dir = Path(f"{mount_point}{CONFIG_DIR}")

    # Ensure the source directory exists before trying to move it.
    if ISO_CONFIG_DIR.exists():
        # Using copytree is safer for directories.
        shutil.copytree(ISO_CONFIG_DIR, target_config_dir)
    else:
        info(f"Configuration directory {ISO_CONFIG_DIR} not found, skipping copy.")
        return

    post_install_script = f"{CONFIG_DIR}/post_install.sh"
    
    # ** API CHANGE **
    # We no longer use a custom `chroot_cmd`. The Installer class
    # provides a safe and reliable way to run commands in the new system.
    info("Executing post-install script...")
    installation.run_in_target(f"chmod +x {post_install_script}")
    installation.run_in_target(f"{post_install_script} {SUDO_USER}")


def perform_installation() -> None:
    """
    Performs the main installation steps using the Installer class API.
    """
    info("Starting base system installation...")
    # ** API CHANGE **
    # The Installer now takes the config object. We retrieve it from storage.
    config = archinstall.storage.config
    
    # The mountpoint is defined in the config, so we pass it to the installer.
    with Installer(config.mountpoint, config) as installation:
        
        # ** LOGIC CHANGE **
        # The installer now handles ALL disk operations.
        # It will partition, format, and mount everything based on `config.disk_config`.
        # We only need to call the high-level installation steps.
        installation.mount_ordered_layout()

        # These steps remain largely the same.
        installation.set_mirrors()
        installation.minimal_installation()
        installation.add_bootloader()
        installation.configure_networking()
        installation.create_users()
        # The root password is now also stored in the config object.
        installation.user_set_pw("root", config.root_password)
        installation.set_timezone()
        installation.activate_time_synchronization()
        # The installer now reads the services to enable from the config.
        for service in config.services:
            installation.enable_service(service)
        installation.genfstab()

        # Pass the installer instance to the configure function
        # so it can run chroot commands.
        configure_system(installation)

        if not config.silent:
            with Tui():
                if MenuItemGroup.yes_no("Do you want to chroot into the new system for manual changes?"):
                    info("You will now be dropped into a shell. Type 'exit' to return.")
                    try:
                        installation.drop_to_shell()
                    except Exception as e:
                        info(f"Could not drop to shell: {e}")


def main():
    """Defines configuration and runs the entire installation process."""
    # ** API CHANGE **
    # Get the global configuration object.
    config = archinstall.storage.config
    
    # Set default values directly on the config object.
    config.packages = ['base', 'linux', 'linux-firmware']
    config.services = ["NetworkManager", "sshd"]
    config.bootloader = Bootloader.SYSTEMD
    config.hostname = "archlinux"
    config.locale_config = models.LocaleConfiguration('en_US.UTF-8', 'en_US')
    config.swap = True
    config.uki = True

    with Tui():
        # This function now correctly populates `config.disk_config`.
        prompt_disk_and_encryption()
        
        # ** API CHANGE **
        # We now configure users directly on the config object.
        global SUDO_USER
        SUDO_USER = ask_user("Sudo user username", "user")
        password = get_password(text="Sudo user password")
        config.users = [User(SUDO_USER, password, sudo=True)]
        
        config.root_password = get_password("Enter root password")
        config.hostname = ask_user("Enter hostname", config.hostname)

        # The menu now reads from and writes to the global config by default.
        GlobalMenu().run()

    # ** API CHANGE **
    # The config object has its own save methods.
    config.save_config()
    config.save_secure_config()
    
    if config.dry_run:
        print("Dry-run selected, exiting.")
        exit(0)

    if not config.silent:
        with Tui():
            if not MenuItemGroup.yes_no("All configuration is set. Do you want to continue?"):
                debug("Installation aborted by user.")
                return

    # ** LOGIC REMOVED **
    # All manual disk handling (apply, mount) is removed.
    # The `Installer` instance will manage this based on the `config.disk_config`.
    
    perform_installation()
    
    info("Installation complete. You can now reboot.")


if __name__ == "__main__":
        
    # Create the temporary config directory if it doesn't exist
    # for the post-install script.
    if not ISO_CONFIG_DIR.exists():
        ISO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Created temporary config directory at {ISO_CONFIG_DIR}")
        # You would place your post_install.sh script here.

    main()

