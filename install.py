from pathlib import Path
from getpass import getpass
import shutil

from archinstall.default_profiles.minimal import MinimalProfile
from archinstall.lib.disk.device_handler import device_handler
from archinstall.lib.disk.filesystem import FilesystemHandler
from archinstall.lib.installer import Installer
from archinstall.lib.models.device_model import (
    DeviceModification,
    DiskEncryption,
    DiskLayoutConfiguration,
    DiskLayoutType,
    EncryptionType,
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

# Warn the user about data loss
print("WARNING: The selected device will be wiped and all data will be lost.")

# Get the list of available devices
devices = device_handler.devices
if not devices:
    raise ValueError("No devices found")

# Display available devices with numbers and sizes
print("Available devices:")
for i, device in enumerate(devices, start=1):
    # FIX: Explicitly load the detailed information for the device.
    # This is necessary to access attributes like `device_info`.
    size_gib = device.device_info.total_size
    print(f"{i}. {device.path} - {size_gib:.2f} GiB")

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

# Prompt user for other installation inputs
sudo_user = input("Enter sudo user username: ")
sudo_password = getpass("Enter sudo user password: ")
root_password = getpass("Enter root password: ")
hostname = input("Enter hostname: ")
encryption_password = getpass("Enter disk encryption password: ")

# Create device modification with wipe
device_modification = DeviceModification(device, wipe=True)

# Define filesystem type
fs_type = FilesystemType('ext4')

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

# Create root partition (ext4, 20 GiB)
root_start = boot_start + boot_length
root_length = Size(20, Unit.GiB, device.device_info.sector_size)
root_partition = PartitionModification(
    status=ModificationStatus.Create,
    type=PartitionType.Primary,
    start=root_start,
    length=root_length,
    mountpoint=None,  # Mounted at / by Installer
    fs_type=fs_type,
    mount_options=[],
)
device_modification.add_partition(root_partition)

# Create home partition (ext4, remaining space)
home_start = root_start + root_length
# REFINEMENT: Set length to 0 to automatically use all remaining space.
# This is more reliable than calculating the size manually.
home_length = Size(0, Unit.B, device.device_info.sector_size)
home_partition = PartitionModification(
    status=ModificationStatus.Create,
    type=PartitionType.Primary,
    start=home_start,
    length=home_length,
    mountpoint=Path('/home'),
    fs_type=fs_type,
    mount_options=[],
)
device_modification.add_partition(home_partition)

# Create disk configuration
disk_config = DiskLayoutConfiguration(
    config_type=DiskLayoutType.Default,
    device_modifications=[device_modification],
)

# Configure disk encryption for root and home partitions
disk_encryption = DiskEncryption(
    encryption_password=Password(plaintext=encryption_password),
    encryption_type=EncryptionType.Luks,
    partitions=[root_partition, home_partition],
    hsm_device=None,
)
disk_config.disk_encryption = disk_encryption

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
    installation.add_additional_packages(['wget', 'git'])

    # Install minimal profile
    profile_config = ProfileConfiguration(MinimalProfile())
    profile_handler.install_profile_config(installation, profile_config)

    # Create sudo user
    user = User(sudo_user, Password(plaintext=sudo_password), True)
    installation.create_users(user)

    # Set root password
    installation.user_set_pw('root', Password(plaintext=root_password))

    # Enable services from old script
    installation.enable_service(['NetworkManager', 'sshd'])

    # Set timezone from old script
    installation.set_timezone('Europe/Oslo')

    # Copy configuration files and run post-install script
    config_source = Path('/tmp/archinstall')
    config_target = mountpoint / 'opt' / 'archinstall'
    config_target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(config_source), str(config_target), dirs_exist_ok=True)
    installation.arch_chroot('chmod +x /opt/archinstall/post_install.sh')
    installation.arch_chroot(f'/opt/archinstall/post_install.sh {sudo_user}')

print("Installation complete. You can now reboot.")

