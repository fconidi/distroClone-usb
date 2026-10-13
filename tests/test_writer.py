import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from distroclone_usb.writer import Runner, assert_same_device, copy_verified, mount_volumes, partition_path


class WriterTest(unittest.TestCase):
    def test_hotplug_replacement_aborts_before_boot_sector_write(self):
        with patch('distroclone_usb.writer.inventory', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'scollegato'):
                assert_same_device('/dev/sdz', 'a' * 64)

    def test_nonzero_command_stops_operation(self):
        with self.assertRaises(RuntimeError):
            Runner(lambda *a, **k: None).run('/usr/bin/false')

    def test_partition_names(self):
        self.assertEqual(partition_path('/dev/sdb', 3), '/dev/sdb3')
        self.assertEqual(partition_path('/dev/mmcblk0', 3), '/dev/mmcblk0p3')

    def test_changed_source_fails_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            source.write_bytes(b'contents')
            fd = os.open(source, os.O_RDONLY)
            try:
                with self.assertRaises(ValueError):
                    copy_verified(fd, Path(folder) / 'target', '0' * 64, lambda *a, **k: None)
            finally:
                os.close(fd)

    def test_copy_never_follows_destination_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder) / 'source', Path(folder) / 'target'
            source.write_bytes(b'original')
            dest.symlink_to(source)
            fd = os.open(source, os.O_RDONLY)
            try:
                with self.assertRaises(FileExistsError):
                    copy_verified(fd, dest, '0' * 64, lambda *a, **k: None)
            finally:
                os.close(fd)
            self.assertEqual(source.read_bytes(), b'original')

    def test_mount_failure_unmounts_only_successful_mounts(self):
        calls = []

        class FakeRunner:
            def run(self, command, *args, **kwargs):
                calls.append((command, args))
                if command == 'mount' and args[-1].endswith('/persist'):
                    raise RuntimeError('mount failure')

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                with mount_volumes('/dev/sdb', Path(folder), FakeRunner()):
                    self.fail('Must not enter after failed mount')
        unmounts = [args[0] for cmd, args in calls if cmd == 'umount']
        self.assertEqual(unmounts, [folder + '/data', folder + '/efi'])

    def test_unmount_failure_is_reported_and_directory_retained(self):
        class FakeRunner:
            def run(self, command, *args, **kwargs):
                if command == 'umount':
                    raise RuntimeError('busy')

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'smontare'):
                with mount_volumes('/dev/sdb', Path(folder), FakeRunner()):
                    pass
            self.assertTrue((Path(folder) / 'data').exists())
