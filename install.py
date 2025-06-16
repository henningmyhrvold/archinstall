import shutil
import subprocess
from pathlib import Path

import archinstall
from archinstall import SysInfo, debug, info
from archinstall.lib import disk, locale, models
from archinstall.lib.interactions.disk_conf import select_devices, suggest_single_disk_layout
from archinstall.tui.menu_item import yes_no
from archinstall.lib.global_menu import GlobalMenu
from archinstall.lib.installer import Installer
from archinstall.lib.models import Bootloader, User
from archinstall.lib.models.network_configuration import NetworkConfiguration
from archinstall.lib.utils.util import get_password
from archinstall.tui import Tui
from archinstall.tui.types import Alignment
from archinstall.tui.curses_menu EditMenu

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

        for partition in suggested_layout.partitions:
            if partition.mountpoint != Path("/boot"):
                partition.encrypted = True
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
    ret = subprocess.run(
        ["arch-chroot", str(MOUNT_POINT), "/bin/bash", "-c", cmd],
        check=False
    )
    if ret.returncode != 0:
        raise RuntimeError(f"Failed to run chroot command: {cmd}")

def configure_system():
    """Copies configuration files and runs the post-install script."""
    info("Copying configuration files to new system")
    target_config_dir = Path(f"{MOUNT_POINT}{CONFIG_DIR}")
    
    target_config_dir.parent.mkdir(parents=True, exist_ok=True)
    
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
    
    with Installer(mountpoint, archinstall.arguments) as installation:
        
        if not installation.is_mounted(str(mountpoint)):
            installation.mount_ordered_layout()

        installation.set_mirrors()
        installation.minimal_installation()
        installation.add_bootloader()
        installation.configure_networking()
        installation.create_users()
        installation.user_set_pw("root", archinstall.arguments.get("--!root-password"))
        installation.set_timezone()
        installation.activate_time_synchronization()
        installation.enable_service()
        installation.genfstab()

        configure_system()

        if not archinstall.arguments.get("--silent"):
            with Tui():
                if yes_no("Do you want to chroot into the new system for manual changes?"):
                    info("You will now be dropped into a shell within the new system. Type 'exit' to return to the installation process.")
                    try:
                        installation.drop_to_shell()
                    except Exception as e:
                        info(f"Could not drop to shell: {e}")

def main():
    """Defines configuration and runs the entire installation process."""
    archinstall.arguments.update({
        "--packages": [],
        "--services": ["NetworkManager", "sshd"],
        "--bootloader": Bootloader.SYSTEMD,
        "--hostname": "archlinux",
        "--locale-config": models.LocaleConfiguration('en_US.UTF-8', 'en_US'),
        "--swap": True,
        "--uki": True,
    })

    with Tui():
        prompt_disk_and_encryption()
        archinstall.arguments["--!users"] = parse_user()
        archinstall.arguments["--!root-password"] = get_password("Enter root password")
        archinstall.arguments["--hostname"] = ask_user("Enter hostname", archinstall.arguments['--hostname'])

        GlobalMenu(data_store=archinstall.arguments).run()

    archinstall.save_config(archinstall.arguments)
    archinstall.save_secure_config(archinstall.arguments)
    
    if archinstall.arguments.get("--dry-run"):
        exit(0)

    if not archinstall.arguments.get("--silent"):
        with Tui():
            if not yes_no("All configuration is set. Do you want to continue with the installation?"):
                debug("Installation aborted by user.")
                return

    # Apply disk layout and mount root partition
    disk_config = archinstall.arguments['--disk-config']
    disk_config.apply()

    # Find and mount the root partition
    for partition in disk_config.partitions:
        if partition.mountpoint == Path('/'):
            root_partition_path = partition.device
            break

    mount_point = Path('/mnt')
    mount_point.mkdir(parents=True, exist_ok=True)
    subprocess.run(['mount', root_partition_path, str(mount_point)], check=True)
    global MOUNT_POINT
    MOUNT_POINT = mount_point

    perform_installation(MOUNT_POINT)
    
    info("Installation complete. You can now reboot.")

if __name__ == "__main__":
    archinstall.set_log_path('/var/log/archinstall')
    main()
