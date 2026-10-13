import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from distroclone_usb.profiles import Profile
from distroclone_usb.shared import prepare_shared


class SharedTest(unittest.TestCase):
    def profile(self, family='debian'):
        return Profile(family, 'test', '/live/vmlinuz', ('/live/initrd.img',),
                       ('boot=live', 'user=admin'), 'persistence')

    def test_shared_is_outside_system_overlay_and_home_link_is_visible(self):
        with tempfile.TemporaryDirectory() as folder, patch('os.chown'):
            root = Path(folder)
            prepare_shared(root, self.profile(), '12345678-1234-1234-1234-123456789abc')
            self.assertEqual((root / 'Shared').stat().st_mode & 0o777, 0o700)
            self.assertEqual(os.readlink(root / 'rw/home/admin/Shared'), '/Shared')
            service = root / 'rw/etc/systemd/system/distroclone-usb-shared.service'
            text = service.read_text()
            self.assertIn('UUID=12345678-1234-1234-1234-123456789abc', text)
            self.assertIn('nosuid,nodev,noexec', text)
            self.assertNotIn('ExecStart=/Shared', text)
            self.assertTrue((service.parent / 'multi-user.target.wants' / service.name).is_symlink())

    def test_casper_uses_upper_overlay(self):
        with tempfile.TemporaryDirectory() as folder, patch('os.chown'):
            prepare_shared(Path(folder), self.profile('casper'), '12345678-1234-1234-1234-123456789abc')
            self.assertTrue((Path(folder) / 'upper/home/admin/Shared').is_symlink())
            self.assertFalse((Path(folder) / 'rw').exists())

    def test_private_creation_umask_does_not_break_live_system_permissions(self):
        with tempfile.TemporaryDirectory() as folder, patch('os.chown'):
            previous = os.umask(0o077)
            try:
                prepare_shared(Path(folder), self.profile(), '12345678-1234-1234-1234-123456789abc')
            finally:
                os.umask(previous)
            for name in ('rw', 'rw/etc', 'rw/etc/systemd', 'rw/etc/systemd/system', 'rw/home'):
                self.assertEqual((Path(folder) / name).stat().st_mode & 0o777, 0o755)

    def test_invalid_uuid_is_rejected_without_creating_files(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                prepare_shared(Path(folder), self.profile(), 'bad; echo injected')
            self.assertEqual(list(Path(folder).iterdir()), [])
