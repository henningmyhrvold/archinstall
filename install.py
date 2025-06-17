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

# Prompt user for installation inputs
device_path = input("Enter the device path (e.g., /dev/sda): ")
sudo_user = input("Enter sudo user username: ")
sudo_password = getpass("Enter sudo user password: ")
root_password = getpass("Enter root password: ")
hostname = input("Enter hostname: ")
encryption_password = getpass("Enter disk encryption password: ")

# Get the device
device = device_handler.get_device(Path(device_path))
if not device:
    raise ValueError('No device found for given path')

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
home_length = device.device_info.total_size - home_start
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
