# Compatibility

Supported profiles in version 0.3.1. Compatibility depends on the structure of each live image.

| ISO family | Support |
|---|---|
| SysLinuxOS / Debian Live with live-boot | Persistence and optional encryption for compatible images |
| Recognized Ubuntu desktop and Linux Mint casper images | Unencrypted persistence |
| Other Debian live-boot derivatives | Depends on image structure |
| MX / antiX and installer-only images | Unsupported |
| ARM, IA32-only UEFI and Secure Boot | Unsupported |

The host requires GRUB i386-pc and x86_64-efi modules. An amd64 Debian/Ubuntu host
is the intended platform. No firmware NVRAM entries or host bootloaders are changed.
Optional LUKS2 encryption is available for compatible Debian Live / SysLinuxOS
images; casper encryption remains rejected. See ENCRYPTION.md for required
initramfs capabilities, PBKDF2/Argon2id boundaries and boot requirements.
Choose persistence size before creation; resizing and
multi-ISO menus are outside this version.

References:
- https://manpages.debian.org/trixie/live-boot-doc/live-boot.7.en.html
- https://manpages.debian.org/trixie/live-boot-doc/persistence.conf.5.en.html
- https://manpages.ubuntu.com/manpages/jammy/man7/casper.7.html
- https://help.ubuntu.com/community/Installation/iso2usb/isoboot
- https://www.gnu.org/software/grub/manual/grub/grub.html
