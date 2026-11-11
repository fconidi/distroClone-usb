"""The window offers a Close button once a USB has been created and verified."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pump(Gtk):
    while Gtk.events_pending():
        Gtk.main_iteration()


@unittest.skipUnless(os.environ.get('DISPLAY'), 'needs a display (run under xvfb-run)')
class CloseButtonTest(unittest.TestCase):
    def run_in_app(self, body):
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        from distroclone_usb import gui
        outcome = []
        app = Gtk.Application(application_id='com.syslinuxos.distroclone_usb_test_close')

        def activate(application):
            try:
                with patch('distroclone_usb.gui.inventory', return_value=[]):
                    window = gui.Window(application)
                    window.show_all()
                    pump(Gtk)
                    body(Gtk, window)
            except Exception as error:  # noqa: BLE001 - reported after the loop
                outcome.append(error)
            finally:
                application.quit()
        app.connect('activate', activate)
        app.run([])
        if outcome:
            raise outcome[0]

    def test_close_appears_only_after_success_and_survives_language_change(self):
        def body(Gtk, window):
            form = window.form
            self.assertFalse(form.close.get_visible())
            window.writing = True
            window.set_busy(True)
            window.finished(True)
            self.assertTrue(form.close.get_visible())
            self.assertTrue(form.close.get_sensitive())
            self.assertIn('disconnect', form.status.get_text())
            form.language.set_active_id('it')
            self.assertIsNot(window.form, form)
            self.assertTrue(window.form.close.get_visible())
            self.assertEqual(window.form.close.get_label(), 'Chiudi')
            window.form.language.set_active_id('en')
            window.create()  # no disk selected: must not start, Close stays
            self.assertTrue(window.form.close.get_visible())
        self.run_in_app(body)

    def test_close_hidden_after_failure_and_closes_window(self):
        def body(Gtk, window):
            window.writing = True
            window.set_busy(True)
            window.writer_error = True
            window.finished(False)
            self.assertFalse(window.form.close.get_visible())
            window.writer_error = False
            window.finished(True)
            closed = []
            window.connect('destroy', lambda *_: closed.append(True))
            window.form.close.clicked()
            pump(Gtk)
            self.assertTrue(closed)
        self.run_in_app(body)


if __name__ == '__main__':
    unittest.main()
