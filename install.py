import shutil
import subprocess
from pathlib import Path

import archinstall
from archinstall import SysInfo, debug, info
from archinstall.lib import disk, locale, models
from archinstall.lib.configuration import ConfigurationOutput
from archinstall.lib.disk.device_model import DiskLayoutConfiguration
from archinstall.lib.global_menu import GlobalMenu
from archinstall.lib.installer import Installer
from archinstall.lib.interactions import select_devices, suggest_single_disk_layout
from archinstall.lib.interactions.general_conf import ask_chroot
from archinstall.lib.mirrors import (
    MirrorConfiguration,
)
from archinstall.lib.models import Bootloader, User
from archinstall.lib.models.network_configuration import NetworkConfiguration
from archinstall.lib.profile import ProfileConfiguration
from archinstall.lib.utils.util import get_password
from archinstall.tui import Alignment, EditMenu, Tui

SUDO_USER = None
CONFIG_DIR = "/opt/archinstall"
ISO_CONFIG_DIR = "/tmp/archinstall"
MOUNT_POINT: str | Path = ""


def ask_user(title="", default_text="") -> str:
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


def prompt_disk_layout(fs_type="ext4", separate_home=False) -> None:
    fs_type = disk.FilesystemType(fs_type)

    devices = select_devices()
    modifications = suggest_single_disk_layout(
        devices[0], filesystem_type=fs_type, separate_home=separate_home
    )

    archinstall.arguments["disk_config"] = disk.DiskLayoutConfiguration(
        config_type=disk.DiskLayoutType.Default, device_modifications=[modifications]
    )


def parse_disk_encryption() -> None:
    modification: DiskLayoutConfiguration = archinstall.arguments["disk_config"]
    partitions: list[disk.PartitionModification] = []

    # encrypt all partitions except the /boot
    for mod in modification.device_modifications:
        partitions += list(
            filter(lambda x: x.mountpoint != Path("/boot"), mod.partitions)
        )

    archinstall.arguments["disk_encryption"] = disk.DiskEncryption(
        encryption_type=disk.EncryptionType.Luks,
        encryption_password=get_password("Enter disk encryption password: "),
        partitions=partitions,
    )


def parse_user():
    global SUDO_USER
    SUDO_USER = ask_user("Sudo user username", "user")
    password = get_password(text="Sudo user password")
    return [User(SUDO_USER, password, sudo=True)]


def chroot_cmd(cmd):
    ret = subprocess.run(
        [
            "arch-chroot",
            MOUNT_POINT,
            "/bin/bash",
            "-c",
            cmd,
        ]
    )
    if ret.returncode != 0:
        raise Exception(f"Failed to run command: {cmd}")


def mv(source, destination):
    shutil.move(source, destination)


def configure_system():
    info("Copying configuration files")
    # Ensure the target directory exists
    Path(f"{MOUNT_POINT}{CONFIG_DIR}").mkdir(parents=True, exist_ok=True)
    
    # Move configuration files
    mv(ISO_CONFIG_DIR, f"{MOUNT_POINT}{CONFIG_DIR}/..")

    chroot_cmd(f"chmod +x {CONFIG_DIR}/post_install.sh")
    info("Starting post install script")
    chroot_cmd(f"{CONFIG_DIR}/post_install.sh {SUDO_USER}")


def perform_installation(mountpoint: Path) -> None:
    """
    Performs the installation steps on a block device.
    """
    info("Starting installation...")
    disk_config: disk.DiskLayoutConfiguration = archinstall.arguments["disk_config"]

    enable_testing = "testing" in archinstall.arguments.get(
        "additional-repositories", []
    )
    enable_multilib = "multilib" in archinstall.arguments.get(
        "additional-repositories", []
    )
    run_mkinitcpio = not archinstall.arguments.get("uki")
    locale_config: locale.LocaleConfiguration = archinstall.arguments["locale_config"]
    disk_encryption: disk.DiskEncryption = archinstall.arguments.get(
        "disk_encryption", None
    )

    with Installer(
        mountpoint,
        disk_config,
        disk_encryption=disk_encryption,
        kernels=archinstall.arguments.get("kernels", ["linux"]),
    ) as installation:
        if disk_config.config_type != disk.DiskLayoutType.Pre_mount:
            installation.mount_ordered_layout()

        installation.sanity_check()

        if disk_config.config_type != disk.DiskLayoutType.Pre_mount:
            if (
                disk_encryption
                and disk_encryption.encryption_type != disk.EncryptionType.NoEncryption
            ):
                installation.generate_key_files()

        if mirror_config := archinstall.arguments.get("mirror_config", None):
            installation.set_mirrors(mirror_config, on_target=False)

        # This installs the base system
        installation.minimal_installation(
            testing=enable_testing,
            multilib=enable_multilib,
            mkinitcpio=run_mkinitcpio,
            hostname=archinstall.arguments.get("hostname"),
            locale_config=locale_config,
        )

        if mirror_config := archinstall.arguments.get("mirror_config", None):
            installation.set_mirrors(mirror_config, on_target=True)

        if archinstall.arguments.get("swap"):
            installation.setup_swap("zram")

        installation.add_bootloader(
            archinstall.arguments["bootloader"], archinstall.arguments.get("uki", False)
        )

        network_config: NetworkConfiguration | None = archinstall.arguments.get(
            "network_config", None
        )

        if network_config:
            network_config.install_network_config(
                installation, archinstall.arguments.get("profile_config", None)
            )

        if users := archinstall.arguments.get("!users", None):
            installation.create_users(users)
        
        # All additional packages will be installed by the post_install.sh script
        if (
            archinstall.arguments.get("packages", None)
            and archinstall.arguments.get("packages", None)[0] != ""
        ):
            installation.add_additional_packages(
                archinstall.arguments.get("packages", None)
            )

        if timezone := archinstall.arguments.get("timezone", None):
            installation.set_timezone(timezone)

        if archinstall.arguments.get("ntp", False):
            installation.activate_time_synchronization()

        if (root_pw := archinstall.arguments.get("!root-password", None)) and len(
            root_pw
        ):
            installation.user_set_pw("root", root_pw)

        if archinstall.arguments.get("services", None):
            installation.enable_service(archinstall.arguments.get("services", []))

        installation.genfstab()

        configure_system()

        if not archinstall.arguments.get("silent"):
            with Tui():
                chroot = ask_chroot()
            if chroot:
                try:
                    installation.drop_to_shell()
                except Exception:
                    pass

        info(
            "For post-installation tips, see https://wiki.archlinux.org/index.php/Installation_guide#Post-installation"
        )

    debug(f"Disk states after installing:\n{disk.disk_layouts()}")


def install():
    # Set sane defaults for a minimal install
    archinstall.arguments["packages"] = [""]
    archinstall.arguments["services"] = ["NetworkManager", "sshd"]
    archinstall.arguments["profile_config"] = None
    archinstall.arguments["audio_config"] = None
    archinstall.arguments["network_config"] = models.NetworkConfiguration(
        models.NicType.NM
    )
    archinstall.arguments["bootloader"] = models.Bootloader.Systemd
    archinstall.arguments["timezone"] = "Europe/Oslo"
    archinstall.arguments["uki"] = True # Using Unified Kernel Images

    with Tui():
        prompt_disk_layout()
        parse_disk_encryption()
        archinstall.arguments["!users"] = parse_user()
        archinstall.arguments["!root-password"] = get_password("Enter root password")
        archinstall.arguments["hostname"] = ask_user("Enter hostname", "arch")
        global_menu = GlobalMenu(data_store=archinstall.arguments)
        global_menu.set_enabled("parallel downloads", True)
        global_menu.run()

    config = ConfigurationOutput(archinstall.arguments)
    config.write_debug()
    config.save()

    if archinstall.arguments.get("dry_run"):
        exit(0)

    if not archinstall.arguments.get("silent"):
        with Tui():
            if not config.confirm_config():
                debug("Installation aborted")
                return install()

    fs_handler = disk.FilesystemHandler(
        archinstall.arguments["disk_config"],
        archinstall.arguments.get("disk_encryption", None),
    )

    fs_handler.perform_filesystem_operations()
    global MOUNT_POINT
    MOUNT_POINT = archinstall.arguments.get("installation.target", Path("/mnt"))
    perform_installation(MOUNT_POINT)
    info("Installation complete. You can now reboot.")


if __name__ == "__main__":
    install()
