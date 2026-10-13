# Compatibility

Version 0.1.0 implements profiles, not a blanket promise for every Debian derivative.

| ISO family | Implementation | Verification |
|---|---|---|
| SysLinuxOS / Debian Live using live-boot | findiso, dedicated ext4 persistence, unique persistence-label, / union | SysLinuxOS 13.2 MATE: real creation, BIOS/UEFI boot and persistence across reboots verified in QEMU/KVM; details in VALIDATION.md |
| Ubuntu desktop / recognized Ubuntu flavors | casper, iso-scan/filename, writable since Ubuntu 20.04; casper-rw for earlier releases | Synthetic ISO/profile tests; real distribution boot pending |
| Linux Mint desktop | casper, writable since Mint 20; casper-rw for earlier releases | Profile parsing implemented; real distribution boot pending |
| Other Debian live-boot derivatives | Same Debian profile when ISO structure and boot entry match | Must validate each image/version |
| MX / antiX | Recognized explicitly | Creation rejected in 0.1 |
| Installer-only / Ubuntu Server | Unsupported | Creation rejected |
| ARM, IA32-only UEFI, Secure Boot | Unsupported | Creation rejected or firmware requirement documented |

The host requires GRUB i386-pc and x86_64-efi modules. An amd64 Debian/Ubuntu host
is the intended platform. No firmware NVRAM entries or host bootloaders are changed.
Persistence is unencrypted in 0.1. Choose its size before creation; resizing and
multi-ISO menus are outside this version.

References:
- https://manpages.debian.org/trixie/live-boot-doc/live-boot.7.en.html
- https://manpages.debian.org/trixie/live-boot-doc/persistence.conf.5.en.html
- https://manpages.ubuntu.com/manpages/jammy/man7/casper.7.html
- https://help.ubuntu.com/community/Installation/iso2usb/isoboot
- https://www.gnu.org/software/grub/manual/grub/grub.html
