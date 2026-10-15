#!/usr/bin/python3
"""Boot only a disposable test USB image prepared with a serial test console.

QEMU has no network or host disk passthrough. Writes a guest marker, then verifies
it across another VM boot. Requires access to /dev/kvm, not host root privileges.
"""

import argparse
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time


ARTIFACTS = Path.home() / '.cache' / 'distroclone-usb' / 'test-artifacts'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--firmware', choices=('bios', 'uefi'), required=True)
    parser.add_argument('--mode', choices=('write', 'read'), required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('--encrypted', action='store_true')
    parser.add_argument('--short-test-key', action='store_true')
    parser.add_argument('--shared', action='store_true')
    parser.add_argument('--interactive', action='store_true', help='Legacy init=/bin/sh test images only')
    parser.add_argument('--reject-password', action='store_true')
    args = parser.parse_args()
    image, log = Path(args.image).resolve(), Path(args.log).resolve()
    if ARTIFACTS not in image.parents or not image.is_file():
        parser.error('Only an existing disposable image under ~/.cache/distroclone-usb/test-artifacts may be used')
    command = ['/usr/bin/qemu-system-x86_64', '-accel', 'kvm', '-cpu', 'host', '-m', '2048',
               '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-no-reboot', '-nic', 'none',
               '-drive', 'if=none,id=stick,format=raw,file=' + str(image),
               '-device', 'qemu-xhci', '-device', 'usb-storage,drive=stick,bootindex=1']
    if args.firmware == 'uefi':
        variables = log.with_suffix('.vars.fd')
        shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', variables)
        command += ['-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
                    '-drive', 'if=pflash,format=raw,file=' + str(variables)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline, transcript, sent = time.monotonic() + 360, bytearray(), False
    prompt_offset = 0
    marker = (b'encrypted volumes could not be unlocked' if args.reject_password else
              b'DCUSB_WRITE_OK' if args.mode == 'write' else b'DCUSB_PERSIST_OK')
    try:
        with log.open('wb') as stream:
            while time.monotonic() < deadline:
                for key, events in selector.select(timeout=.5):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        break
                    stream.write(chunk)
                    stream.flush()
                    transcript.extend(chunk)
                    if args.encrypted:
                        tail = bytes(transcript[prompt_offset:])
                        if b'Enter passphrase for' in tail or b'distroClone USB: enter USB passphrase: ' in tail:
                            process.stdin.write(b'WRONG TEST PASSWORD\n' if args.reject_password else (b'Abcd1234Efgh\n' if args.short_test_key else b'distroClone TEST USB 2026 only\n'))
                            process.stdin.flush()
                            prompt_offset = len(transcript)
                    if args.interactive and not args.reject_password and not sent and (b'job control turned off' in transcript or b'\n# ' in transcript
                                     or (b'Disposable test console.' in transcript and b'# ' in transcript)):
                        if args.mode == 'write':
                            script = ("printf 'persisted-20261013' > /var/lib/distroclone-usb-probe; "
                                      "sync; printf 'DCUSB_%s\\n' WRITE_OK; ")
                        else:
                            script = ("test \"$(cat /var/lib/distroclone-usb-probe)\" = persisted-20261013 "
                                      "&& printf 'DCUSB_%s\\n' PERSIST_OK; ")
                        if args.shared:
                            shared_check = 'test -f /Shared/live-write && ' if args.mode == 'read' else ''
                            script += shared_check + ("systemctl is-active distroclone-usb-shared.service && findmnt /Shared && "
                                       "test \"$(cat /Shared/from-host.deb)\" = DCUSB_HOST_SHARED_MARKER && "
                                       "test -L /home/admin/Shared && "
                                       "runuser -u admin -- sh -c 'test -r /Shared/from-host.deb && touch /Shared/live-write' && "
                                       "printf 'DCUSB_%s\\n' SHARED_OK; ")
                        script += 'cat /proc/mounts; sync; echo b > /proc/sysrq-trigger\n'
                        time.sleep(.3)
                        encoded = script.encode()
                        for offset in range(0, len(encoded), 32):
                            process.stdin.write(encoded[offset:offset + 32])
                            process.stdin.flush()
                            time.sleep(.02)
                        sent = True
                if args.reject_password and marker in transcript:
                    break
                if process.poll() is not None and not selector.get_map():
                    break
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        if marker not in transcript:
            raise AssertionError(f'Boot/persistence probe failed; see {log}')
        if args.reject_password and any(value in transcript for value in
                (b'DCUSB_WRITE_OK', b'DCUSB_PERSIST_OK', b'DCUSB_SHARED_OK')):
            raise AssertionError('Failed unlock reached a persistent session')
        if args.shared and not args.reject_password and b'DCUSB_SHARED_OK' not in transcript:
            raise AssertionError(f'Shared folder probe failed; see {log}')
        print(f'PASS: {args.firmware} / {args.mode}: {marker.decode()}')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        selector.close()


if __name__ == '__main__':
    main()
