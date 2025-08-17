import os
from pathlib import Path
from getpass import getpass
import subprocess
import shutil
import time
import re

from archinstall.default_profiles.minimal import MinimalProfile
from archinstall.lib.disk.device_handler import device_handler
from archinstall.lib.disk.filesystem import FilesystemHandler
from archinstall.lib.installer import Installer
from archinstall.lib.models.device import (
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
from archinstall.lib.models import Bootloader
from archinstall.lib.models.profile import ProfileConfiguration
from archinstall.lib.models.users import Password, User
from archinstall.lib.profile.profiles_handler import profile_handler

# Define local mirror addresses (manually set these before running the script)
PACMAN_MIRROR = "192.168.1.100"
AUR_MIRROR = "192.168.1.100"

# Check for UEFI mode
if not os.path.exists('/sys/firmware/efi'):
    raise SystemExit("Error: This script requires a UEFI system. BIOS systems are not supported.")

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
sudo_user = input_with_default("Enter sudo user username", "henning")
use_local_mirrors = input_with_default("Use local offline mirrors for pacman and AUR?", "No").lower().startswith('y')
sudo_password = getpass("Enter sudo user password: ")
root_password = getpass("Enter root password: ")
encryption_password = getpass("Enter disk encryption password: ")

# Create device modification with wipe
device_modification = DeviceModification(device, wipe=True)

# Define filesystem type
fs_type = FilesystemType('ext4')

# Get total disk size as a Size object
total_disk_size = device.device_info.total_size

# Create EFI System Partition (FAT32, 1024 MiB, mounted at /boot)
boot_start = Size(1, Unit.MiB, device.device_info.sector_size)
boot_length = Size(1024, Unit.MiB, device.device_info.sector_size)
boot_partition = PartitionModification(
    status=ModificationStatus.Create,
    type=PartitionType.Primary,
    start=boot_start,
    length=boot_length,
    mountpoint=Path('/boot'),
    fs_type=FilesystemType.Fat32,
    flags=[PartitionFlag.ESP],
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

# Configure disk encryption for root partition
disk_encryption = DiskEncryption(
    encryption_password=Password(plaintext=encryption_password),
    encryption_type=EncryptionType.Luks,
    partitions=[root_partition],
    hsm_device=None,
)
disk_config.disk_encryption = disk_encryption

# Perform filesystem operations
fs_handler = FilesystemHandler(disk_config)
fs_handler.perform_filesystem_operations(show_countdown=False)

# Get UUID of the encrypted root partition
encrypted_uuid = subprocess.check_output(['blkid', '-s', 'UUID', '-o', 'value', root_partition.dev_path]).decode().strip()

# Define mountpoint
mountpoint = Path('/mnt')

# Detect GPU driver for early KMS
lspci_output = subprocess.check_output(['lspci']).decode().lower()
driver = None
if 'intel' in lspci_output and 'vga' in lspci_output:
    driver = 'i915'
elif ('amd' in lspci_output or 'ati' in lspci_output) and 'vga' in lspci_output:
    driver = 'amdgpu'
elif 'nvidia' in lspci_output and 'vga' in lspci_output:
    driver = 'nouveau'

# Perform the installation
with Installer(
    mountpoint,
    disk_config,
    kernels=['linux'],
) as installation:
    # Mount the filesystem layout
    # The mount_ordered_layout() function will automatically create parent
    # directories like /mnt/boot as needed.
    installation.mount_ordered_layout()

    # Configure local mirrors for pacman if selected
    if use_local_mirrors:
        pacman_conf = mountpoint / 'etc' / 'pacman.conf'
        with open(pacman_conf, 'w') as f:
            f.write(f'''
[options]
HoldPkg     = pacman glibc
Architecture = auto
CheckSpace
SigLevel    = Required DatabaseOptional
LocalFileSigLevel = Optional

[core]
Server = http://{PACMAN_MIRROR}/$repo/os/$arch

[extra]
Server = http://{PACMAN_MIRROR}/$repo/os/$arch

[community]
Server = http://{PACMAN_MIRROR}/$repo/os/$arch
''')

    # Perform minimal installation with specified hostname
    installation.minimal_installation(hostname=hostname)

    # Configure local mirrors for paru if selected
    if use_local_mirrors:
        paru_conf = mountpoint / 'etc' / 'paru.conf'
        with open(paru_conf, 'w') as f:
            f.write(f'''
[options]
PacmanConf = /etc/pacman.conf
AURonly
SkipReview

[bin]
Server = http://{AUR_MIRROR}/aur
''')

    # Configure kernel cmdline for encryption
    cmdline_path = mountpoint / 'etc' / 'kernel' / 'cmdline'
    cmdline_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cmdline_path, 'w') as f:
        f.write(f'cryptdevice=UUID={encrypted_uuid}:cryptroot root=/dev/mapper/cryptroot rw quiet splash loglevel=3 rd.udev.log_priority=3 vt.global_cursor_default=0 plymouth.use-simpledrm\n')

    # Configure mkinitcpio preset for UKI
    preset_dir = mountpoint / 'etc' / 'mkinitcpio.d'
    preset_dir.mkdir(parents=True, exist_ok=True)
    preset_path = preset_dir / 'linux.preset'
    with open(preset_path, 'w') as f:
        f.write('''
# mkinitcpio preset file for the 'linux' package

ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux"

PRESETS=('default' 'fallback')

default_uki="/boot/EFI/Linux/arch-linux.efi"
default_options="--splash /usr/share/systemd/bootctl/splash-arch.bmp"

fallback_uki="/boot/EFI/Linux/arch-linux-fallback.efi"
fallback_options="-S autodetect"
''')

    # Add additional packages
    installation.add_additional_packages(['systemd-ukify', 'networkmanager', 'openssh', 'iwd', 'plymouth'])

    # Install systemd-boot bootloader for a UEFI system
    installation.add_bootloader(Bootloader.Systemd)

    # Create EFI/Linux directory for UKIs
    efi_linux_dir = mountpoint / 'boot' / 'EFI' / 'Linux'
    efi_linux_dir.mkdir(parents=True, exist_ok=True)

    # Configure mkinitcpio hooks for Plymouth
    mkinitcpio_conf = mountpoint / 'etc' / 'mkinitcpio.conf'
    with open(mkinitcpio_conf, 'a') as f:
        f.write('\nHOOKS=(base udev autodetect modconf kms plymouth block encrypt filesystems keyboard fsck)\n')
        if driver:
            f.write(f'MODULES=({driver})\n')

    # Set Plymouth default theme
    installation.arch_chroot('plymouth-set-default-theme -R spinner')

    # Configure Plymouth daemon
    plymouthd_conf = mountpoint / 'etc' / 'plymouth' / 'plymouthd.conf'
    plymouthd_conf.parent.mkdir(parents=True, exist_ok=True)
    with open(plymouthd_conf, 'w') as f:
        f.write('[Daemon]\nTheme=spinner\nShowDelay=0\n')

    # Generate UKIs
    installation.arch_chroot('mkinitcpio -P')

    # Configure loader.conf
    loader_conf = mountpoint / 'boot' / 'loader' / 'loader.conf'
    with open(loader_conf, 'w') as f:
        f.write('''
default arch-linux*.efi
timeout 1
console-mode max
editor no
''')

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
    installation.enable_service(['NetworkManager.service', 'sshd.service', 'iwd.service'])

    # Set timezone
    installation.set_timezone('Europe/Oslo')
    
    installation.setup_swap("zram")
    
    # Create a swap file inside the encrypted root filesystem
    # This provides swap space for memory-intensive tasks and is encrypted along with the root partition
    print("Creating swap file...")
    SWAP_SIZE = "8G"
    installation.arch_chroot(f'fallocate -l {SWAP_SIZE} /swapfile')
    installation.arch_chroot('chmod 600 /swapfile')
    installation.arch_chroot('mkswap /swapfile')
    
    # Set swap file priority to 5 to ensure it is used after zram
    installation.arch_chroot('echo "/swapfile none swap pri=5 0 0" >> /etc/fstab')

    # Copy configuration files
    config_source = Path('/tmp/archinstall')
    config_target = mountpoint / 'opt' / 'archinstall'
    config_target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(config_source), str(config_target), dirs_exist_ok=True)
    
    # Make the post-install script executable within the new system
    installation.arch_chroot('chmod +x /opt/archinstall/post_install.sh')

# Remove old Ubuntu entries, uncomment and rename if you want to clean up old boot entries in the UEFI boot meny.
#print("\n--- Customizing EFI boot entry ---")
#efiboot_output = subprocess.check_output(['efibootmgr', '-v']).decode()
#lines = efiboot_output.splitlines()
#
#ubuntu_nums = []
#for line in lines:
#    if 'Ubuntu' in line:
#        match = re.match(r'Boot([0-9A-F]{4})', line)
#        if match:
#            ubuntu_nums.append(match.group(1))
#
#for boot_num in ubuntu_nums:
#    subprocess.call(['efibootmgr', '--delete-bootnum', '--bootnum', boot_num])
#    print(f"Removed old Ubuntu boot entry {boot_num}")

# Run the post-install script using subprocess to stream its output
print("\n--- Running post-install script ---")
command = [
    'arch-chroot',
    str(mountpoint),
    '/opt/archinstall/post_install.sh',
    sudo_user
]

try:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    if process.stdout:
        for line in iter(process.stdout.readline, ''):
            print(line, end='')

    process.wait()

    if process.returncode == 0:
        print("\n--- Post-install script completed successfully ---")
        print("\nInstallation complete. You can now reboot.")
    else:
        print(f"\n--- Post-install script failed with exit code {process.returncode} ---")
        print("Please check the output above for errors.")

except Exception as e:
    print(f"\nAn unexpected error occurred: {e}")
