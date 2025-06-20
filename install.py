from pathlib import Path
from getpass import getpass
import subprocess
import shutil
import time

from archinstall.default_profiles.minimal import MinimalProfile
from archinstall.lib.disk.device_handler import device_handler
from archinstall.lib.disk.filesystem import FilesystemHandler
from archinstall.lib.installer import Installer
from archinstall.lib.models.device_model import (
    DeviceModification,
    DiskLayoutConfiguration,
    DiskLayoutType,
    FilesystemType,
    ModificationStatus,
    PartitionFlag,
    PartitionModification,
    PartitionType,
    Size,
    Unit,
)
from archinstall.lib.models.profile_model import ProfileConfiguration
from archinstall.lib.models.users import Password, User
from archinstall.lib.profile.profiles_handler import profile_handler

# Custom input function to provide default values
def input_with_default(prompt, default):
    user_input = input(f"{prompt} [{default}]: ")
    return user_input.strip() or default

# Get the list of available devices
devices = device_handler.devices
if not devices:
    raise ValueError("No devices found")

# Automatically select the device if there is only one
if len(devices) == 1:
    selected_device = devices[0]
    print(f"Only one device found: {selected_device.device_info.path} - {selected_device.device_info.total_size.format_highest()}")
else:
    # Display available devices with numbers and sizes
    print("Available devices:")
    for i, device in enumerate(devices, start=1):
        size_gib = device.device_info.total_size.format_highest()
        print(f"{i}. {device.device_info.path} - {size_gib}")

    # Prompt the user to select a device by number
    while True:
        try:
            choice = int(input("Enter the number of the device to use: "))
            if 1 <= choice <= len(devices):
                selected_device = devices[choice - 1]
                break
            else:
                print("Invalid number. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

# Use the selected device
device = selected_device

# Prompt user for installation inputs with defaults
hostname = input_with_default("Enter hostname", "arch")
sudo_user = input_with_default("Enter sudo user username", "hm")
sudo_password = getpass("Enter sudo user password: ")
root_password = getpass("Enter root password: ")

# Create device modification with wipe
device_modification = DeviceModification(device, wipe=True)

# Define filesystem type
fs_type = FilesystemType('ext4')

# Get total disk size as a Size object
total_disk_size = device.device_info.total_size

# Create boot partition (FAT32, 512 MiB)
boot_start = Size(1, Unit.MiB, device.device_info.sector_size)
boot_length = Size(512, Unit.MiB, device.device_info.sector_size)
boot_partition = PartitionModification(
    status=ModificationStatus.Create,
    type=PartitionType.Primary,
    start=boot_start,
    length=boot_length,
    mountpoint=Path('/boot'),
    fs_type=FilesystemType.Fat32,
    flags=[PartitionFlag.BOOT],
)
device_modification.add_partition(boot_partition)

# Create root partition (ext4, remaining space)
root_start = boot_start + boot_length
root_length = total_disk_size - root_start - Size(1, Unit.MiB, device.device_info.sector_size)
root_partition = PartitionModification(
    status=ModificationStatus.Create,
    type=PartitionType.Primary,
    start=root_start,
    length=root_length,
    mountpoint=Path('/'),
    fs_type=fs_type,
    mount_options=[],
)
device_modification.add_partition(root_partition)

# Create disk configuration
disk_config = DiskLayoutConfiguration(
    config_type=DiskLayoutType.Default,
    device_modifications=[device_modification],
)

# Perform filesystem operations
fs_handler = FilesystemHandler(disk_config)
fs_handler.perform_filesystem_operations(show_countdown=False)

# Define mountpoint
mountpoint = Path('/mnt')

# Perform the installation
with Installer(
    mountpoint,
    disk_config,
    kernels=['linux'],
) as installation:
    # Mount the filesystem layout
    installation.mount_ordered_layout()

    # Perform minimal installation with specified hostname
    installation.minimal_installation(hostname=hostname)

    # Add additional packages
    installation.add_additional_packages(['networkmanager', 'openssh', 'git'])

    # Install minimal profile
    profile_config = ProfileConfiguration(MinimalProfile())
    profile_handler.install_profile_config(installation, profile_config)

    # Create sudo user
    user = User(sudo_user, Password(plaintext=sudo_password), True)
    installation.create_users(user)

    # Set root password
    root_user = User('root', Password(plaintext=root_password), False)
    installation.set_user_password(root_user)

    # Enable services
    installation.enable_service(['NetworkManager.service', 'sshd.service'])

    # Set timezone
    installation.set_timezone('Europe/Oslo')

    # Copy configuration files and run post-install script
    config_source = Path('/tmp/archinstall')
    config_target = mountpoint / 'opt' / 'archinstall'
    config_target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(config_source), str(config_target), dirs_exist_ok=True)
    installation.arch_chroot('chmod +x /opt/archinstall/post_install.sh')
    installation.arch_chroot(f'/opt/archinstall/post_install.sh {sudo_user}')

print("Installation complete. You can now reboot.")
