import ast
import json
import os
from pathlib import Path
import shutil
import string
import subprocess
import tempfile
import unittest

from distroclone_usb.i18n import CATALOGS, LANGUAGES, ROWS, get_language, set_language, tr


class TranslationTest(unittest.TestCase):
    def tearDown(self):
        set_language('en')

    def test_all_five_catalogs_complete_and_placeholders_preserved(self):
        self.assertEqual(set(CATALOGS), {'en', 'it', 'es', 'fr', 'de'})
        formatter = string.Formatter()
        fields = lambda text: {name for literal, name, spec, conversion in formatter.parse(text) if name}
        for key, row in ROWS.items():
            self.assertEqual(len(row), 4, key)
            for code in LANGUAGES:
                with self.subTest(code=code, key=key):
                    self.assertTrue(CATALOGS[code][key].strip())
                    self.assertEqual(fields(key), fields(CATALOGS[code][key]))

    def test_interface_and_literal_errors_are_in_catalog(self):
        root = Path(__file__).resolve().parents[1]
        files = list((root / 'distroclone_usb').glob('*.py')) + [root / 'helper.py']
        for path in files:
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in {'tr', 'label'} and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    value = node.args[0].value
                    if value != 'distroClone USB':
                        self.assertIn(value, ROWS, (path.name, value))

    def test_language_selection_changes_errors_and_actions(self):
        for code, expected in [('en', 'Cancel'), ('it', 'Annulla'), ('es', 'Cancelar'),
                               ('fr', 'Annuler'), ('de', 'Abbrechen')]:
            set_language(code)
            self.assertEqual(get_language(), code)
            self.assertEqual(tr('Cancel'), expected)
        with self.assertRaises(ValueError):
            set_language('xx')

    @unittest.skipUnless(shutil.which('grub-script-check'), 'GRUB required')
    def test_localized_boot_menus_have_valid_grub_syntax(self):
        from distroclone_usb.profiles import Profile, grub_config
        profile = Profile('debian', 'Debian', '/live/vmlinuz', ('/live/initrd.img',),
                          ('boot=live',), 'persistence')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'grub.cfg'
            for code in LANGUAGES:
                set_language(code)
                path.write_text(grub_config(profile, 'dcusb123', 'dc-p123'))
                result = subprocess.run(['grub-script-check', str(path)], capture_output=True)
                self.assertEqual(result.returncode, 0, (code, result.stderr))

    @unittest.skipIf(os.geteuid() == 0, 'Tests the unprivileged helper rejection')
    def test_helper_errors_follow_explicit_language(self):
        helper = Path(__file__).resolve().parents[1] / 'helper.py'
        for code in LANGUAGES:
            set_language(code)
            result = subprocess.run(['/usr/bin/python3', '-I', str(helper), '--iso', '/nonexistent.iso',
                                     '--device', '/dev/not-a-disk', '--persistence-mib', '512',
                                     '--expected-id', '0'*64, '--confirm', 'not-a-disk',
                                     '--sha256', '0'*64, '--language', code],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['message'],
                             tr('Creating a USB requires administrative authorization.'))
