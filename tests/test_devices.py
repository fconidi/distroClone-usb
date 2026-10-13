import copy
import unittest

from distroclone_usb.devices import device_token, eligible_disks, validate_target
from distroclone_usb.layout import make_layout


MIB = 1024 * 1024
USB = {'name': '/dev/sdb', 'type': 'disk', 'size': 16000 * MIB, 'model': 'USB Disk',
       'serial': 'ABC', 'tran': 'usb', 'rm': True, 'ro': False, 'maj:min': '8:16',
       'mountpoints': [], 'children': [
           {'name': '/dev/sdb1', 'type': 'part', 'maj:min': '8:17', 'mountpoints': []}]}


class DevicesTest(unittest.TestCase):
    def test_usb_is_eligible_and_requires_identity_and_confirmation(self):
        self.assertEqual(len(eligible_disks([USB])), 1)
        validate_target([USB], '/dev/sdb', device_token(USB), 'sdb')
        for token, confirm in [('bad', 'sdb'), (device_token(USB), 'sda')]:
            with self.assertRaises(ValueError):
                validate_target([USB], '/dev/sdb', token, confirm)

    def test_internal_readonly_partition_and_mounted_targets_are_rejected(self):
        for changes in [{'tran': 'nvme', 'rm': False}, {'ro': True}, {'type': 'part'},
                        {'mountpoints': ['/']}, {'mountpoints': ['/media/user/USB']},
                        {'mountpoints': ['[SWAP]']}]:
            disk = copy.deepcopy(USB)
            disk.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_target([disk], '/dev/sdb', device_token(disk), 'sdb')

    def test_child_system_mapper_or_source_blocks_whole_disk(self):
        disk = copy.deepcopy(USB)
        disk['children'][0]['children'] = [
            {'name': '/dev/mapper/root', 'type': 'crypt', 'maj:min': '253:0',
             'mountpoints': ['/']}]
        with self.assertRaises(ValueError):
            validate_target([disk], '/dev/sdb', device_token(disk), 'sdb')
        with self.assertRaises(ValueError):
            validate_target([USB], '/dev/sdb', device_token(USB), 'sdb', source_dev='8:17')

    def test_disk_replacement_changes_token(self):
        disk = dict(USB, serial='OTHER')
        self.assertNotEqual(device_token(disk), device_token(USB))

    def test_layout_alignment_and_capacity_512_and_4096(self):
        for sector in (512, 4096):
            layout = make_layout(16000 * MIB, 4000 * MIB, 8000, sector)
            self.assertEqual(len(layout.partitions), 4)
            previous_end = 0
            for part in layout.partitions:
                self.assertEqual(part.start * sector % MIB, 0)
                self.assertGreaterEqual(part.start, previous_end)
                previous_end = part.start + part.sectors
            self.assertLessEqual(previous_end * sector, 16000 * MIB - MIB)
            self.assertEqual(layout.partitions[-1].sectors * sector, 8000 * MIB)

    def test_too_small_iso_or_persistence_and_bad_sector_fail(self):
        for args in [(5000*MIB, 4000*MIB, 4000, 512), (16000*MIB, 4000*MIB, 0, 512),
                     (16000*MIB, 4000*MIB, 8000, 1024)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                make_layout(*args)
