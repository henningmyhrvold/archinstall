import shutil
import subprocess
from pathlib import Path

import archinstall
from archinstall import SysInfo, debug, info
from archinstall.lib import locale, models
from archinstall.lib.global_menu import GlobalMenu
from archinstall.lib.installer import Installer
from archinstall.lib.interaction import (
    ask_chroot,
    select_devices,
    suggest_single_disk_layout,
    yes_no,
)
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
    This function combines the logic of the original `prompt_disk_layout` and `parse_disk_encryption`.
    """
    # Select the target block device
    block_devices = select_devices()
    
    # Suggest a layout based on user preference
    suggested_layout = suggest_single_disk_layout(
        block_devices[0], filesystem_type=models.FileSystemType(fs_type), separate_home=separate_home
    )

    # Ask if the user wants to encrypt the disk
    if yes_no("Do you want to enable disk encryption?"):
        encryption_password = get_password("Enter disk encryption password: ")
        
        # Define the encryption configuration
        encryption_config = {
            "encryption_type": "luks",
            "password": encryption_password,
            "partitions": []
        }

        # Mark all partitions for encryption except for /boot
        for device in suggested_layout.values():
            for partition in device.get('partitions', []):
                if partition.get('mountpoint') != Path("/boot"):
                    partition['encrypted'] = True
                    # Add the partition object itself to the encryption config
                    encryption_config["partitions"].append(partition)
        
        archinstall.arguments['--disk-encryption'] = encryption_config

    # Store the final disk layout configuration
    archinstall.arguments['--disk-config'] = suggested_layout


def parse_user() -> list[User]:
    """Prompts for and creates a sudo user."""
    global SUDO_USER
    SUDO_USER = ask_user("Sudo user username", "user")
    password = get_password(text="Sudo user password")
    return [User(SUDO_USER, password, sudo=True)]


def chroot_cmd(cmd: str) -> None:
    """Executes a command inside the arch-chroot environment."""
    ret = subprocess.run(
        ["arch-chroot", MOUNT_POINT, "/bin/bash", "-c", cmd],
        check=False  # We check the return code manually
    )
    if ret.returncode != 0:
        raise archinstall.lib.exceptions.ArchinstallError(f"Failed to run chroot command: {cmd}")


def configure_system():
    """Copies configuration files into the new system and runs a post-install script."""
    info("Copying configuration files")
    target_config_dir = Path(f"{MOUNT_POINT}{CONFIG_DIR}")
    target_config_dir.mkdir(parents=True, exist_ok=True)
    
    # Move configuration files from the ISO to the new system
    shutil.move(ISO_CONFIG_DIR, target_config_dir.parent)

    post_install_script = f"{CONFIG_DIR}/post_install.sh"
    chroot_cmd(f"chmod +x {post_install_script}")
    info("Starting post install script")
    chroot_cmd(f"{post_install_script} {SUDO_USER}")


def perform_installation(mountpoint: Path) -> None:
    """Performs the main installation steps using the Installer class."""
    info("Starting installation...")
    
    with Installer(mountpoint, archinstall.arguments) as installation:
        # Mount the partitions (if not pre-mounted)
        # This is now handled by run_disk_operations, but we ensure drives are mounted.
        if not installation.is_mounted(mountpoint):
             installation.mount_ordered_layout()

        # Set mirrors for the live environment (for pacstrap)
        if mirror_config := archinstall.arguments.get("--mirror-config", None):
            installation.set_mirrors(mirror_config, on_target=False)

        # Install base system and packages
        installation.minimal_installation()

        # Set mirrors on the target system
        if mirror_config := archinstall.arguments.get("--mirror-config", None):
            installation.set_mirrors(mirror_config, on_target=True)

        # Install bootloader
        installation.add_bootloader()

        # Configure network
        if network_config := archinstall.arguments.get("--network-config", None):
            network_config.install_network_config(
                installation, archinstall.arguments.get("--profile-config", None)
            )

        # Create users
        if users := archinstall.arguments.get("--!users", None):
            installation.create_users(users)
        
        # Set root password
        if root_pw := archinstall.arguments.get("--!root-password", None):
            installation.user_set_pw("root", root_pw)

        # Install additional packages (if any)
        if packages := archinstall.arguments.get("--packages", []):
            installation.add_additional_packages(packages)

        # Configure system settings
        if timezone := archinstall.arguments.get("--timezone", None):
            installation.set_timezone(timezone)
        
        if archinstall.arguments.get("--ntp", False):
            installation.activate_time_synchronization()

        if services := archinstall.arguments.get("--services", []):
            installation.enable_service(services)

        # Generate fstab
        installation.genfstab()

        # Run custom system configuration
        configure_system()

        # Offer to chroot into the new system
        if not archinstall.arguments.get("--silent"):
            with Tui():
                if ask_chroot():
                    try:
                        installation.drop_to_shell()
                    except Exception as e:
                        info(f"Could not drop to shell: {e}")

    info("For post-installation tips, see https://wiki.archlinux.org/index.php/Installation_guide#Post-installation")
    debug(f"Disk states after installing:\n{archinstall.lib.disk.disk_layouts()}")


def install():
    """Main function to define configuration and run the installation."""
    # Set defaults using the new dictionary-based argument system
    archinstall.arguments.update({
        "--packages": [],  # All additional packages will be installed by the post_install.sh script
        "--services": ["NetworkManager", "sshd"],
        "--profile-config": None,
        "--audio-config": None,
        "--network-config": models.NetworkConfiguration(nic_type=models.NicType.NM),
        "--bootloader": Bootloader.SYSTEMD,
        "--timezone": "Europe/Oslo",
        "--uki": True,
        "--hostname": "arch",
        "--locale-config": models.LocaleConfiguration('en_US.UTF-8', 'en_US'),
        "--swap": True,
    })

    with Tui():
        prompt_disk_and_encryption()
        archinstall.arguments["--!users"] = parse_user()
        archinstall.arguments["--!root-password"] = get_password("Enter root password")
        archinstall.arguments["--hostname"] = ask_user("Enter hostname", archinstall.arguments['--hostname'])

        # The global menu allows users to review and change any setting before proceeding
        global_menu = GlobalMenu(data_store=archinstall.arguments)
        global_menu.set_enabled("parallel downloads", True)
        global_menu.run()

    # Save user configuration for debugging and re-use
    archinstall.save_config(archinstall.arguments)
    archinstall.save_secure_config(archinstall.arguments)
    
    if archinstall.arguments.get("--dry-run"):
        exit(0)

    if not archinstall.arguments.get("--silent"):
        with Tui():
            if not yes_no("Do you want to continue with the installation?"):
                debug("Installation aborted by user.")
                return

    # Perform all disk operations (partitioning, formatting, encryption)
    # This is the modern replacement for FilesystemHandler
    mounts = run_disk_operations(archinstall.arguments)
    
    global MOUNT_POINT
    # The main installation mountpoint is the one for the root directory ('/')
    MOUNT_POINT = next(mount for mount in mounts if mount.mountpoint == Path('/'))

    perform_installation(MOUNT_POINT)
    
    info("Installation complete. You can now reboot.")


if __name__ == "__main__":
    install()
