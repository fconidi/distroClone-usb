#!/usr/bin/python3
"""Exercise the real GTK window without invoking the privileged writer."""

import argparse
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from distroclone_usb.gui import Window, apply_style
from distroclone_usb.gui_widgets import confirm_creation
from distroclone_usb.iso import ISOImage
from distroclone_usb.profiles import detect_profile
from distroclone_usb.i18n import LANGUAGES, tr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--iso')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    failures = []
    app = Gtk.Application(application_id='com.syslinuxos.distroclone_usb_test')
    def activate(application):
        apply_style()
        with patch('distroclone_usb.gui.inventory', return_value=[]):
            window = Window(application)
        window.show_all()
        def check():
            try:
                assert not window.form.create.get_sensitive()
                assert window.form.devices.get_active() == -1
                disk = {'name': '/dev/sdz', 'type': 'disk', 'size': 16 * 1024**3,
                        'model': 'Virtual USB — test only', 'serial': 'TEST-001',
                        'tran': 'usb', 'rm': True, 'ro': False, 'maj:min': '8:240',
                        'mountpoints': [], 'children': []}
                with patch('distroclone_usb.gui.inventory', return_value=[disk]):
                    window.refresh()
                assert window.form.devices.get_active() == -1
                files = {'/live/vmlinuz', '/live/initrd.img', '/live/filesystem.squashfs',
                         '/EFI/BOOT/BOOTX64.EFI'}
                profile = detect_profile(files, ['linux /live/vmlinuz boot=live user=admin quiet\n'
                                                 'initrd /live/initrd.img'])
                image = ISOImage('/example/SysLinuxOS-Live.iso', 5 * 1024**3, 'a'*64, profile)
                if args.iso:
                    from distroclone_usb.iso import inspect_iso
                    image = inspect_iso(args.iso)
                    window.form.iso.set_filename(image.path)
                window.iso_ready(image, None)
                window.form.devices.set_active(0)
                assert window.form.create.get_sensitive()
                window.form.encryption.set_active_id('all')
                assert not window.form.create.get_sensitive()
                window.form.password.set_text('distroClone TEST USB 2026 only')
                assert not window.form.create.get_sensitive()
                window.form.confirm_password.set_text('distroClone TEST USB 2026 only')
                assert window.form.create.get_sensitive()
                with patch('distroclone_usb.gui.inventory', return_value=[disk]):
                    window.form.language.set_active_id('de')
                assert window.form.encryption.get_active_id() == 'all'
                assert window.form.password.get_text() == ''
                assert not window.form.create.get_sensitive()
                window.form.encryption.set_active_id('none')
                window.form.persistence.set_value(14)
                assert not window.form.create.get_sensitive()
                window.form.persistence.set_value(4)
                assert window.form.create.get_sensitive()
                for code in LANGUAGES:
                    with patch('distroclone_usb.gui.inventory', return_value=[disk]):
                        window.form.language.set_active_id(code)
                    assert window.form.create.get_label() == tr('Create USB…')
                    assert window.form.devices.get_active() == 0
                    assert window.form.persistence.get_value() == 4
                    assert window.form.create.get_sensitive()
                with patch('distroclone_usb.gui.inventory', return_value=[disk]):
                    window.form.language.set_active_id('it')
                window.set_busy(True)
                assert not window.form.language.get_sensitive()
                window.set_busy(False)
                window.form.iso_info.set_text(f'SysLinuxOS / Debian Live · {image.size/1024**3:.2f} GiB · /live/vmlinuz')
                window.form.status.set_text('Pronto: ISO riconosciuta e USB selezionata')
                window.form.progress.set_fraction(0)
                def cancel_dialog():
                    for widget in Gtk.Window.list_toplevels():
                        if isinstance(widget, Gtk.Dialog) and widget.get_widget_for_response(Gtk.ResponseType.OK):
                            assert not widget.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive()
                            widget.response(Gtk.ResponseType.CANCEL)
                    return False
                GLib.timeout_add(150, cancel_dialog)
                assert not confirm_creation(window, image, disk, 4096)
                def capture():
                    pixbuf = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0,
                                                       window.get_allocated_width(), window.get_allocated_height())
                    pixbuf.savev(str(output / 'desktop.png'), 'png', [], [])
                    icon = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(Path(__file__).resolve().parents[1] /
                                                                 'packaging/distroclone-usb.svg'), 512, 512, True)
                    icon.savev(str(output / 'logo.png'), 'png', [], [])
                    window.destroy()
                    application.quit()
                    return False
                GLib.timeout_add(300, capture)
            except Exception as error:
                failures.append(repr(error))
                window.destroy()
                application.quit()
            return False
        GLib.timeout_add(200, check)
    app.connect('activate', activate)
    app.run([])
    if failures:
        raise AssertionError(failures)
    print('GTK workflow passed: empty state, explicit selection, capacity, EN/IT/ES/FR/DE switch, confirmation cancel, screenshot')


if __name__ == '__main__':
    main()
