from pathlib import Path
from getpass import getpass
import subprocess
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

# Custom input function to provide default values
def input_with_default(prompt, default):
    user_input = input(f"{prompt} [{default}]: ")
    return user_input.strip() or default

# Warn the user about data loss
print("WARNING: The selected device will be wiped and all data will be lost.")

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
sudo_user = input_with_default("Enter sudo user username", "user")
sudo_password = getpass("Enter sudo user password: ")
root_password = getpass("Enter root password: ")
hostname = input_with_default("Enter hostname", "arch")
encryption_password = getpass("Enter disk encryption password: ")

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

# Create root partition (ext4, 20 GiB)
root_start = boot_start + boot_length
root_length = Size(20, Unit.GiB, device.device_info.sector_size)
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

# Calculate remaining space for home partition
home_start = root_start + root_length
used_size = boot_length + root_length
remaining_size = total_disk_size - used_size - Size(1, Unit.MiB, device.device_info.sector_size)

# Ensure there is enough space for the home partition (minimum 1 MiB)
min_home_size = Size(1, Unit.MiB, device.device_info.sector_size)
if remaining_size < min_home_size:
    raise ValueError(
        f"Disk is too small: {total_disk_size.format_highest()} available, "
        f"but {(used_size.format_highest())} required for boot and root partitions."
    )

home_length = remaining_size
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

# Create disk configuration (this object is used by the FilesystemHandler and Installer)
disk_config = DiskLayoutConfiguration(
    config_type=DiskLayoutType.Default,
    device_modifications=[device_modification],
)

# Configure disk encryption
disk_encryption = DiskEncryption(
    encryption_password=Password(plaintext=encryption_password),
    encryption_type=EncryptionType.Luks,
    partitions=[root_partition, home_partition],
    hsm_device=None,
)
disk_config.disk_encryption = disk_encryption

# Create and Commit the Partition Layout
# This uses the clean, direct method on the DeviceHandler.
print(f"Writing partition table to {device.device_info.path}...")
device_handler.partition(device_modification)
print("...partition table written.")

# After the initial wipe and partitioning, set wipe=False.
# This prevents the FilesystemHandler from wiping the disk again.
device_modification.wipe = False

# Force the system to recognize the new partitions
# This prevents the race condition.
print("Waiting for kernel to recognize new partitions...")
subprocess.run(['partprobe', device.device_info.path], check=True)
subprocess.run(['udevadm', 'settle'], check=True)
print("...partitions recognized.")

# Perform filesystem operations on the now-existing partitions
# This will now only format and encrypt, without wiping.
print("Formatting partitions and setting up encryption...")
fs_handler = FilesystemHandler(disk_config)
fs_handler.perform_filesystem_operations(show_countdown=False)
# This print statement might not be reached if the script continues correctly
# print("...filesystem operations complete.")

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
    installation.add_additional_packages(['networkmanager','openssh','wget', 'git'])

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
