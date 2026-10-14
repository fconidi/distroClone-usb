import unittest

from distroclone_usb.profiles import UnsupportedISO, detect_profile, grub_config


DEBIAN_FILES = {'/live/vmlinuz', '/live/initrd.img', '/live/filesystem.squashfs',
                '/EFI/BOOT/BOOTX64.EFI'}
DEBIAN_CFG = '''menuentry "Live" {
linux /live/vmlinuz boot=live components username=admin quiet splash
initrd /live/initrd.img
}'''


class ProfilesTest(unittest.TestCase):
    def test_debian_preserves_live_user_and_adds_persistence(self):
        p = detect_profile(DEBIAN_FILES, [DEBIAN_CFG], 'SysLinuxOS')
        self.assertEqual(p.family, 'debian')
        cfg = grub_config(p, 'dcusb123', 'dc-p123')
        self.assertIn('username=admin', cfg)
        self.assertIn('findiso=/distroclone/live.iso', cfg)
        self.assertIn('persistence persistence-label=dc-p123', cfg)
        self.assertIn('nopersistence', cfg)
        self.assertIn('nomodeset', cfg)

    def test_syslinux_configuration_is_supported(self):
        p = detect_profile(DEBIAN_FILES, ['''label live
kernel /live/vmlinuz
append initrd=/live/initrd.img boot=live components locales=it_IT.UTF-8 quiet'''])
        self.assertIn('locales=it_IT.UTF-8', p.arguments)

    def test_casper_release_controls_label(self):
        files = {'/casper/vmlinuz', '/casper/initrd', '/casper/filesystem.squashfs',
                 '/EFI/BOOT/BOOTX64.EFI'}
        cfg = 'linux /casper/vmlinuz boot=casper quiet ---\ninitrd /casper/initrd'
        for release, label in [('Ubuntu 24.04 LTS', 'writable'),
                               ('Ubuntu 18.04 LTS', 'casper-rw')]:
            with self.subTest(release=release):
                p = detect_profile(files, [cfg], release)
                self.assertEqual(p.persistence_label, label)
                self.assertIn('iso-scan/filename=', grub_config(p, 'dc123', label))

    def test_unknown_casper_version_is_rejected(self):
        files = {'/casper/vmlinuz', '/casper/initrd', '/casper/root.squashfs',
                 '/EFI/BOOT/BOOTX64.EFI'}
        with self.assertRaises(UnsupportedISO):
            detect_profile(files, ['linux /casper/vmlinuz boot=casper\ninitrd /casper/initrd'])

    def test_installer_and_mx_are_rejected(self):
        for files in [{'/install.amd/vmlinuz'}, {'/antiX/linuxfs', '/antiX/vmlinuz'}]:
            with self.subTest(files=files), self.assertRaises(UnsupportedISO):
                detect_profile(files, [])

    def test_untrusted_grub_code_is_never_copied(self):
        p = detect_profile(DEBIAN_FILES, [DEBIAN_CFG.replace('quiet splash',
                           'quiet; reboot $(evil) ${evil} foo="x y"')])
        self.assertNotIn('reboot', grub_config(p, 'dc123', 'dc-p123'))
        self.assertNotIn('evil', grub_config(p, 'dc123', 'dc-p123'))

    def test_live_server_installer_is_rejected(self):
        files = {'/casper/vmlinuz', '/casper/initrd', '/casper/root.squashfs',
                 '/EFI/BOOT/BOOTX64.EFI'}
        with self.assertRaises(UnsupportedISO):
            detect_profile(files, ['linux /casper/vmlinuz boot=casper\ninitrd /casper/initrd'],
                           'Ubuntu-Server 24.04 LTS')
