"""GTK form widgets and destructive confirmation dialog."""

from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf

from .i18n import LANGUAGES, get_language, tr


def asset_path():
    installed = Path('/usr/share/icons/hicolor/scalable/apps/distroclone-usb.svg')
    return installed if installed.exists() else Path(__file__).resolve().parent.parent / 'packaging/distroclone-usb.svg'


def label(text, style=None):
    widget = Gtk.Label(label=tr(text), xalign=0)
    widget.set_line_wrap(True)
    if style:
        widget.get_style_context().add_class(style)
    return widget


MODE_LABELS = {'none': 'No encryption', 'persistence': 'Encrypt persistence and shared files',
               'all': 'Encrypt ISO, persistence and shared files'}


class Form(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_border_width(24)
        header = Gtk.Box(spacing=18)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(asset_path()), 76, 76, True)
        header.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        titles.pack_start(label('distroClone USB', 'app-title'), False, False, 0)
        titles.pack_start(label('Your system, ready to travel.', 'dim-label'), False, False, 0)
        header.pack_start(titles, True, True, 0)
        language_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        language_box.pack_start(label('Language'), False, False, 0)
        self.language = Gtk.ComboBoxText()
        for code, name in LANGUAGES.items():
            self.language.append(code, code.upper() + ' · ' + name)
        self.language.set_active_id(get_language())
        self.language.get_accessible().set_name(tr('Language'))
        language_box.pack_start(self.language, False, False, 0)
        header.pack_end(language_box, False, False, 0)
        self.pack_start(header, False, False, 0)
        self.pack_start(Gtk.Separator(), False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body_scroll = Gtk.ScrolledWindow()
        body_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body_scroll.set_min_content_height(220)
        body_scroll.add(body)
        self.pack_start(body_scroll, True, True, 0)
        body.pack_start(label('1. Live ISO', 'heading'), False, False, 0)
        self.iso = Gtk.FileChooserButton(title=tr('Choose an ISO image'), action=Gtk.FileChooserAction.OPEN)
        image_filter = Gtk.FileFilter()
        image_filter.set_name('ISO (*.iso)')
        image_filter.add_pattern('*.iso')
        image_filter.add_pattern('*.ISO')
        self.iso.add_filter(image_filter)
        body.pack_start(self.iso, False, False, 0)
        self.iso_info = label('Choose a Debian Live, SysLinuxOS, Ubuntu or Linux Mint desktop ISO.', 'dim-label')
        body.pack_start(self.iso_info, False, False, 0)
        body.pack_start(label('2. USB drive', 'heading'), False, False, 0)
        device_row = Gtk.Box(spacing=8)
        self.devices = Gtk.ComboBoxText()
        self.devices.set_hexpand(True)
        self.refresh = Gtk.Button(label=tr('Refresh'))
        self.unmount = Gtk.Button(label=tr('Unmount volumes'))
        for widget, expand in ((self.devices, True), (self.refresh, False), (self.unmount, False)):
            device_row.pack_start(widget, expand, expand, 0)
        body.pack_start(device_row, False, False, 0)
        self.device_info = label('Select a USB drive explicitly.', 'dim-label')
        body.pack_start(self.device_info, False, False, 0)
        body.pack_start(label('3. Persistence', 'heading'), False, False, 0)
        persistence_row = Gtk.Box(spacing=12)
        self.persistence = Gtk.SpinButton.new_with_range(.5, 1024, .5)
        self.persistence.set_digits(1)
        self.persistence.set_value(4)
        self.persistence.set_numeric(True)
        persistence_row.pack_start(self.persistence, False, False, 0)
        persistence_row.pack_start(label('GiB reserved for applications, settings and files.'), True, True, 0)
        body.pack_start(persistence_row, False, False, 0)
        body.pack_start(label('Shared files are available in the Shared folder in your live home.'), False, False, 0)
        body.pack_start(label('4. Security', 'heading'), False, False, 0)
        self.encryption = Gtk.ComboBoxText()
        for mode, title in MODE_LABELS.items():
            self.encryption.append(mode, tr(title))
        self.encryption.set_active_id('none')
        body.pack_start(self.encryption, False, False, 0)
        self.password = Gtk.Entry(visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD)
        self.password.set_max_length(512)
        self.confirm_password = Gtk.Entry(visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD)
        self.confirm_password.set_max_length(512)
        for title, widget in (('Passphrase', self.password), ('Confirm passphrase', self.confirm_password)):
            body.pack_start(label(title), False, False, 0)
            widget.get_accessible().set_name(tr(title))
            body.pack_start(widget, False, False, 0)
            widget.set_sensitive(False)
        self.security_info = label('No encryption', 'dim-label')
        body.pack_start(self.security_info, False, False, 0)
        self.pack_start(label('All existing USB data will be erased. Secure Boot must be disabled.', 'warning-text'), False, False, 0)
        self.status = label('Ready. Choose an ISO and a USB drive.')
        self.pack_start(self.status, False, False, 0)
        self.progress = Gtk.ProgressBar(show_text=True)
        self.pack_start(self.progress, False, False, 0)
        self.create = Gtk.Button(label=tr('Create USB…'))
        self.create.get_style_context().add_class('suggested-action')
        self.create.set_size_request(-1, 42)
        actions = Gtk.Box(spacing=10)
        actions.pack_start(self.create, True, True, 0)
        self.cancel = Gtk.Button(label=tr('Cancel'))
        self.cancel.get_style_context().add_class('destructive-action')
        self.cancel.set_sensitive(False)
        actions.pack_start(self.cancel, False, False, 0)
        self.pack_start(actions, False, False, 0)
        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        self.log.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(110)
        scroll.add(self.log)
        expander = Gtk.Expander(label=tr('Operation log'))
        expander.add(scroll)
        self.pack_start(expander, False, False, 0)


def confirm_creation(parent, image, disk, persistence_mib, mode="none"):
    name = Path(disk['name']).name
    dialog = Gtk.Dialog(title=tr('Erase and create USB'), transient_for=parent, modal=True)
    dialog.add_button(tr('Cancel'), Gtk.ResponseType.CANCEL)
    erase = dialog.add_button(tr('Erase and create USB'), Gtk.ResponseType.OK)
    erase.get_style_context().add_class('destructive-action')
    erase.set_sensitive(False)
    content = dialog.get_content_area()
    content.set_border_width(20)
    content.set_spacing(14)
    summary = (tr('This permanently erases every partition and file on:') + '\n\n'
               f'{disk["name"]} — {disk.get("model") or "USB"}\n'
               f'{disk["size"] / 1024**3:.1f} GiB · {tr("Serial")}: {disk.get("serial") or "—"}\n\n'
               f'{tr("ISO")}: {Path(image.path).name}\n'
               f'{tr("Profile")}: {image.profile.family}\n'
               f'{tr("Persistence")}: {persistence_mib / 1024:.1f} GiB\n'
               f'{tr("Encryption")}: {tr(MODE_LABELS[mode])}')
    content.add(label(summary))
    content.add(label(tr('Type the device name to confirm:') + ' ' + name))
    entry = Gtk.Entry()
    entry.connect('changed', lambda widget: erase.set_sensitive(widget.get_text() == name))
    content.add(entry)
    dialog.show_all()
    entry.grab_focus()
    approved = dialog.run() == Gtk.ResponseType.OK and entry.get_text() == name
    dialog.destroy()
    return approved
