"""Unprivileged desktop. All GTK updates happen on the main thread."""

import json
import resource
from pathlib import Path
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from .crypto import validate_encryption
from .devices import device_token, eligible_disks, inventory, mounts, validate_target
from .gui_widgets import Form, asset_path, confirm_creation
from .i18n import get_language, set_language, tr
from .iso import inspect_iso
from .layout import make_layout

from .writer_client import HELPER, start_writer
PHASES = {'inspect': ('Authentication / validating ISO', 0, .05),
          'erase': ('Clearing previous USB contents', .05, .10),
          'partition': ('Partitioning and formatting', .15, .10),
          'copy': ('Copying ISO', .25, .45),
          'verify': ('Verifying USB copy', .70, .20),
          'boot': ('Installing BIOS / UEFI boot', .90, .10)}


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        super().__init__(application=app, title='distroClone USB')
        self.set_default_size(760, 740)
        self.set_icon_from_file(str(asset_path()))
        self.image, self.disks, self.busy, self.writing = None, [], False, False
        self.build_form()
        self.connect('delete-event', self.close_requested)
        self.refresh()

    def build_form(self):
        self.form = Form()
        self.add(self.form)
        self.form.iso.connect('file-set', self.choose_iso)
        self.form.refresh.connect('clicked', self.refresh)
        self.form.unmount.connect('clicked', self.unmount)
        self.form.devices.connect('changed', self.selection_changed)
        self.form.persistence.connect('value-changed', self.selection_changed)
        self.form.encryption.connect('changed', self.security_changed)
        self.form.password.connect('changed', self.selection_changed)
        self.form.confirm_password.connect('changed', self.selection_changed)
        self.form.create.connect('clicked', self.create)
        self.form.language.connect('changed', self.change_language)

    def change_language(self, widget):
        code = widget.get_active_id()
        if not code or code == get_language() or self.busy:
            return
        disk = self.selected()
        selected = disk['name'] if disk else None
        filename, size = self.form.iso.get_filename(), self.form.persistence.get_value()
        mode = self.form.encryption.get_active_id()
        buffer = self.form.log.get_buffer()
        log = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        set_language(code)
        previous = self.form
        self.remove(previous)
        previous.destroy()
        self.build_form()
        self.form.persistence.set_value(size)
        self.form.encryption.set_active_id(mode)
        if filename:
            self.form.iso.set_filename(filename)
        self.refresh()
        for index, item in enumerate(self.disks):
            if item['name'] == selected:
                self.form.devices.set_active(index)
                break
        if self.image:
            self.iso_ready(self.image, None)
        self.form.log.get_buffer().set_text(log)
        if mode != "none":
            self.form.status.set_text(tr("Re-enter the passphrase after changing language."))
        self.show_all()

    def append_log(self, text):
        buffer = self.form.log.get_buffer()
        buffer.insert(buffer.get_end_iter(), text + '\n')
        # Bound a long operation's in-memory log.
        if buffer.get_line_count() > 600:
            buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_line(100))

    def error(self, message):
        self.form.status.set_text(tr('Error') + ': ' + str(message))
        self.append_log(str(message))

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.form.iso, self.form.devices, self.form.refresh,
                       self.form.persistence, self.form.unmount, self.form.language, self.form.encryption):
            widget.set_sensitive(not busy)
        self.security_changed()

    def security_changed(self, *args):
        mode = self.form.encryption.get_active_id() or "none"
        for widget in (self.form.password, self.form.confirm_password):
            widget.set_sensitive(mode != "none" and not self.busy)
        if mode == "none":
            self.form.password.set_text("")
            self.form.confirm_password.set_text("")
        help_text = {
            "none": 'No encryption: ISO, shared files and system changes remain readable.',
            "persistence": 'Encrypted persistence: shared files and system changes require a password; ISO remains readable.',
            "all": 'Full encryption: ISO and private data are encrypted; boot code remains readable. US boot keyboard. GRUB and Linux ask separately.'}
        text = tr(help_text[mode])
        if mode != "none":
            text += "\n" + tr('Use a passphrase of at least {minimum} characters.').format(minimum=20 if mode == "all" else 12)
            text += "\n" + tr('Encrypted creation clears the entire USB first and may take longer. Forgotten passphrases cannot be recovered.')
        self.form.security_info.set_text(text)
        self.selection_changed()

    def selected(self):
        index = self.form.devices.get_active()
        return self.disks[index] if 0 <= index < len(self.disks) else None

    def selection_changed(self, *args):
        disk = self.selected()
        valid = False
        if disk:
            self.form.device_info.set_text(tr('Volumes mounted: unmount before creating the USB.')
                                          if mounts(disk) else tr('USB ready'))
        if disk and self.image and not self.busy:
            try:
                validate_target([disk], disk['name'], device_token(disk), Path(disk['name']).name)
                make_layout(disk['size'], self.image.size, self.persistence_mib())
                validate_encryption(self.image.profile, self.form.encryption.get_active_id(), self.form.password.get_text())
                if self.form.encryption.get_active_id() != "none" and self.form.password.get_text() != self.form.confirm_password.get_text():
                    raise ValueError(tr("Passwords do not match."))
                valid = True
                self.form.device_info.set_text(tr('USB ready') + f' · {self.persistence_mib()/1024:.1f} GiB · ' + tr('Persistence'))
            except ValueError as error:
                self.form.device_info.set_text(str(error))
        self.form.create.set_sensitive(valid)
        self.form.unmount.set_sensitive(bool(disk and mounts(disk) and not self.busy))

    def persistence_mib(self):
        return round(self.form.persistence.get_value() * 1024)

    def refresh(self, *args):
        try:
            self.disks = eligible_disks(inventory())
            self.form.devices.remove_all()
            for disk in self.disks:
                self.form.devices.append_text(f'{disk["name"]} · {(disk.get("model") or "USB").strip()} · {disk["size"]/1024**3:.1f} GiB')
            self.form.devices.set_active(-1)
            self.form.device_info.set_text(tr('Select a USB drive explicitly.') if self.disks
                                          else tr('No USB drive found. Connect one and refresh.'))
            self.selection_changed()
        except Exception as error:
            self.error(error)

    def choose_iso(self, *args):
        path = self.form.iso.get_filename()
        self.image = None
        self.set_busy(True)
        self.form.status.set_text(tr('Inspecting ISO and computing SHA-256…'))
        self.form.progress.set_fraction(0)
        def work():
            try:
                last = [-1]
                def progress(done, size):
                    percent = int(done * 100 / size)
                    if percent != last[0]:
                        GLib.idle_add(self.form.progress.set_fraction, done / size)
                        last[0] = percent
                image = inspect_iso(path, progress)
                GLib.idle_add(self.iso_ready, image, None)
            except Exception as error:
                GLib.idle_add(self.iso_ready, None, str(error))
        threading.Thread(target=work, daemon=True).start()

    def iso_ready(self, image, error):
        self.image = image
        self.set_busy(False)
        if error:
            self.form.iso_info.set_text(str(error))
            self.error(error)
        else:
            self.form.iso_info.set_text(f'{image.profile.family} · {image.size/1024**3:.2f} GiB · {image.profile.kernel}')
            self.form.status.set_text(tr('ISO recognized') + ': ' + Path(image.path).name)
            self.append_log('SHA-256: ' + image.sha256)

    def unmount(self, *args):
        disk = self.selected()
        if not disk:
            return
        # Do not offer unmounting system mounts even on a USB-root host.
        volumes = mounts(disk)
        if any(not mount.startswith(('/media/', '/run/media/')) for _, mount in volumes):
            self.error(tr('Unmount non-desktop volumes manually. No operation performed.'))
            return
        self.set_busy(True)
        def work():
            failure = None
            try:
                for name in sorted({name for name, mount in volumes}):
                    result = subprocess.run(['/usr/bin/udisksctl', 'unmount', '--block-device', name],
                                            capture_output=True, text=True, timeout=60)
                    if result.returncode:
                        raise RuntimeError(result.stderr.strip())
            except Exception as error:
                failure = str(error)
            GLib.idle_add(self.unmounted, failure)
        threading.Thread(target=work, daemon=True).start()

    def unmounted(self, failure):
        self.set_busy(False)
        self.refresh()
        if failure:
            self.error(failure)

    def create(self, *args):
        disk, image, size = self.selected(), self.image, self.persistence_mib()
        if not disk or not image or self.busy:
            return
        if not Path(HELPER).exists():
            self.error(tr('Install the Debian package before creating a USB.'))
            return
        mode = self.form.encryption.get_active_id()
        password = self.form.password.get_text() if mode != "none" else None
        validate_encryption(image.profile, mode, password)
        if password is not None and password != self.form.confirm_password.get_text():
            self.error(tr("Passwords do not match."))
            return
        if not confirm_creation(self, image, disk, size, mode):
            return
        command = ['--iso', image.path, '--device', disk['name'],
                   '--persistence-mib', str(size), '--expected-id', device_token(disk),
                   '--confirm', Path(disk['name']).name, '--sha256', image.sha256,
                   '--language', get_language(), '--encrypt-mode', mode]
        self.form.password.set_text("")
        self.form.confirm_password.set_text("")
        self.writing = True
        self.set_busy(True)
        self.form.progress.set_fraction(0)
        self.form.status.set_text(tr('Authentication / validating ISO'))
        def work(password):
            completed = False
            try:
                process = start_writer(command, password)
                password = None
                for line in process.stdout:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        GLib.idle_add(self.append_log, line.strip())
                        continue
                    completed = completed or event.get('event') == 'done'
                    GLib.idle_add(self.on_event, event)
                code = process.wait()
                GLib.idle_add(self.finished, code == 0 and completed)
            except Exception as error:
                GLib.idle_add(self.error, tr('Cannot start the USB writer.') + ' ' + str(error))
                GLib.idle_add(self.finished, False)
        threading.Thread(target=work, args=(password,), daemon=True).start()

    def on_event(self, event):
        if event.get('event') == 'progress':
            title, start, weight = PHASES.get(event.get('phase'), PHASES['inspect'])
            fraction = start + weight * max(0, min(1, event.get('fraction', 0)))
            self.form.progress.set_fraction(fraction)
            self.form.progress.set_text(f'{fraction:.0%}')
            self.form.status.set_text(tr(title))
        elif event.get('event') == 'error':
            self.error(event.get('message', ''))
        elif event.get('event') == 'log':
            self.append_log(event.get('message', ''))

    def finished(self, success):
        self.writing = False
        self.set_busy(False)
        self.refresh()
        text = tr('USB created and verified. You can disconnect it.' if success
                  else 'Creation failed. The USB may be incomplete.')
        self.form.status.set_text(text)
        self.append_log(text)
        if success:
            self.form.progress.set_fraction(1)
            self.form.progress.set_text('100%')

    def close_requested(self, *args):
        if self.writing:
            self.form.status.set_text(tr('USB creation is running. Please wait before closing.'))
        return self.writing


def run():
    application = Gtk.Application(application_id='com.syslinuxos.distroclone_usb')
    def activate(app):
        apply_style()
        window = Window(app)
        window.show_all()
    application.connect('activate', activate)
    return application.run([])


def apply_style():
    css = Gtk.CssProvider()
    css.load_from_data(b'.app-title { font-size: 26px; font-weight: bold; } '
                      b'.heading { font-weight: bold; }')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                           Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
