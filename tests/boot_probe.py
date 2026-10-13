#!/usr/bin/python3
"""Boot only a disposable test USB image prepared with init=/bin/sh.

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--firmware', choices=('bios', 'uefi'), required=True)
    parser.add_argument('--mode', choices=('write', 'read'), required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()
    image, log = Path(args.image).resolve(), Path(args.log).resolve()
    if '.test-artifacts' not in image.parts or not image.is_file():
        parser.error('Only an existing disposable .test-artifacts image may be used')
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
    deadline, transcript, sent = time.monotonic() + 150, bytearray(), False
    marker = b'DCUSB_WRITE_OK' if args.mode == 'write' else b'DCUSB_PERSIST_OK'
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
                    if not sent and (b'job control turned off' in transcript or b'\n# ' in transcript):
                        if args.mode == 'write':
                            script = ("printf 'persisted-20261013' > /var/lib/distroclone-usb-probe; "
                                      "sync; printf 'DCUSB_%s\\n' WRITE_OK; ")
                        else:
                            script = ("test \"$(cat /var/lib/distroclone-usb-probe)\" = persisted-20261013 "
                                      "&& printf 'DCUSB_%s\\n' PERSIST_OK; ")
                        script += 'cat /proc/mounts; sync; echo b > /proc/sysrq-trigger\n'
                        process.stdin.write(script.encode())
                        process.stdin.flush()
                        sent = True
                if process.poll() is not None and not selector.get_map():
                    break
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        if marker not in transcript:
            raise AssertionError(f'Boot/persistence probe failed; see {log}')
        print(f'PASS: {args.firmware} / {args.mode}: {marker.decode()}')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        selector.close()


if __name__ == '__main__':
    main()
