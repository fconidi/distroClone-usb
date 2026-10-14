# Changelog

## 0.3.1 — 2026-10-14

- Capitalize the SysLinuxOS Tools menu entry as DistroClone USB.

## 0.3.0 — 2026-10-13

- Use quick formatting for encrypted creation, without overwriting the whole USB.
- Accept passphrases from 12 characters in both encrypted modes.
- Add Cancel with a private helper control pipe and cleanup of mounts/LUKS maps.
- Prevent child tools from consuming control input and handle cancelled open/mount
  commands whose kernel operation already succeeded.

## 0.2.1 — 2026-10-13

- Install an XDG menu drop-in for SysLinuxOS Tools, matching existing suite tools.

## 0.2.0 — 2026-10-13

- Shared directory visible at /Shared and in the persistent live user's home.
- Optional LUKS2 encryption of persistence/Shared or ISO plus all private data.
- Debian Live / SysLinuxOS initramfs capability checks before target writes.
- EN/IT/ES/FR/DE encryption controls, phrase confirmation and security explanations.
- Passwords sent only through stdin; encrypted creation clears logical sectors.
- Preserve initramfs script ordering and explicitly select decrypted live media.
- Full encryption uses PBKDF2 for GRUB compatibility and requires a long ASCII
  phrase; minimal boot code remains readable. Casper encryption is not enabled.

## 0.1.0 — 2026-10-13

### Added
- GTK desktop in English, Italian, Spanish, French and German, with an in-app language selector, explicit USB selection and typed erasure confirmation.
- Debian live-boot and recognized Ubuntu/Linux Mint casper persistence profiles.
- GPT USB layout, BIOS boot and unsigned removable x86-64 UEFI boot.
- SHA-256 source and destination verification; fresh device and capacity checks.
- Read-only ISO inspection, device listing and creation planning commands.
- Original distroClone USB SVG logo, desktop integration and Debian package build.

### Limitations
- MX/antiX, Secure Boot and non-x86-64 images are outside this first version.
