# Shared files and encryption

Every newly created USB has a `Shared` directory on its persistence volume.
In a persistent live session, open **Shared** in the live user's home or `/Shared`.
Files copied there from another Linux system are visible in both places.
System changes remain in `rw` (Debian) or `upper` (casper). Do not modify those
internal directories or `work` by hand. Shared is private to live UID 1000.
It uses the persistence space selected in the application; there is no separate
public FAT/exFAT partition. Windows does not read this ext4 directory natively.

## Choose a mode before creation

| Mode | Protected at rest | Still readable without the passphrase |
|---|---|---|
| No encryption | Nothing | ISO, persistence and Shared |
| Encrypt persistence and shared files | Settings, installed applications, personal files and Shared | Original ISO and boot code |
| Encrypt ISO, persistence and shared files | ISO plus all persistent/private contents | Minimal BIOS/EFI loader and its configuration |

Encryption requires a compatible Debian Live / SysLinuxOS ISO containing
cryptsetup, askpass, live-boot and dm-crypt in its initramfs. The application checks
these before any target write. Encrypted casper/Ubuntu/Mint creation is currently
rejected. Unencrypted profiles remain available for recognized casper images.

The persistence volume uses LUKS2 with Argon2id. Full mode also encrypts the ISO
volume with LUKS2/PBKDF2, supported by the installed GRUB 2.12. Both volumes use
the same passphrase: an offline attacker can target the PBKDF2 volume, so the
Argon2id volume does not increase the effective resistance of that shared phrase.
Use a long, unpredictable phrase. The minimum is 12 characters for both encrypted modes. Full encryption requires
ASCII characters. The early boot keyboard uses US
layout; letters, digits and spaces avoid punctuation layout differences.

Full mode asks separately in GRUB and in Linux. The Linux prompt unlocks both
required volumes. A temporary session unlocks the ISO only and does not expose
persistent Shared. Persistence-only mode prompts in Linux for persistent boots.
Three failed Linux unlock attempts stop booting; reboot to retry. No key is stored
on the USB, and a forgotten passphrase cannot be recovered by this tool.

The desktop sends the phrase to the fixed administrative helper through stdin.
It is never put in command arguments, environment variables, logs or key files.
Core dumps are disabled in the desktop and helper. Changing the interface
language clears the phrase fields. Python and GTK do not
guarantee elimination of every transient memory copy; encryption protects data
at rest, not a compromised running machine.

## Cancel creation

The Cancel button requests a graceful stop. Wait for the helper to finish closing
its filesystems and encrypted mappings; do not unplug the USB while it is still
cleaning up. The USB may be incomplete and should be recreated before use.
Cancellation works through the private control pipe to this helper only, without
requiring a second administrator prompt. If the desktop exits, the closed control
pipe also stops its helper. A pending administrator-authentication dialog may
close before any writer is started. Diagnostics report cleanup failures.

## Boundaries

Creation uses quick partitioning/formatting and does not overwrite the whole
USB. Existing files are removed from the new layout, but old plaintext may remain
in unused sectors. Encryption protects newly written contents; this operation
is not secure erasure of previous data. The tool does not encrypt an existing USB in place or preserve its files.
Back them up before recreating it.

The minimal boot area remains unencrypted. This feature does not authenticate
that area or prevent a modified bootloader from stealing the phrase. Keep control
of the USB. Secure Boot remains unsupported and must be disabled.
Other Linux desktops can unlock LUKS volumes through their disk/file manager and
then open Shared. Unlock the persistence volume, rather than copying private
files onto the readable boot area or the ISO volume in persistence-only mode.

## Per la pendrive già creata con 0.1

La nuova cartella Shared e la cifratura si applicano alle USB create dalla nuova
versione. Non vengono aggiunte automaticamente alla chiavetta esistente.
I quattro `.deb` già verificati restano nella radice del suo volume persistente:
vedi [USB-FILES.md](USB-FILES.md). Salvali prima di ricreare la USB; dopo la
creazione copiali nella cartella `Shared` del volume persistente, sbloccandolo se
cifrato. Nella live persistente li troverai nella Home, attraverso il link Shared.
