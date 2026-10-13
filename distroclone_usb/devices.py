"""Device inventory and fail-closed eligibility rules, shared by UI and helper."""

import hashlib
import json
import os
from pathlib import Path
import subprocess


def walk(node):
    yield node
    for child in node.get('children', []):
        yield from walk(child)


def inventory():
    result = subprocess.run(['/usr/bin/lsblk', '--json', '--bytes', '--paths',
                             '--output', 'NAME,TYPE,SIZE,MODEL,SERIAL,TRAN,RM,RO,MAJ:MIN,MOUNTPOINTS'],
                            check=True, capture_output=True, text=True,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}, timeout=20)
    disks = json.loads(result.stdout)['blockdevices']
    for disk in disks:
        sequence = Path('/sys/class/block') / Path(disk['name']).name / 'diskseq'
        disk['diskseq'] = sequence.read_text().strip() if sequence.exists() else ''
    return disks


def device_token(disk):
    fields = [disk.get(k) for k in ('name', 'maj:min', 'size', 'serial', 'diskseq')]
    return hashlib.sha256(json.dumps(fields, separators=(',', ':')).encode()).hexdigest()


def mounts(disk):
    return [(node['name'], mount) for node in walk(disk)
            for mount in (node.get('mountpoints') or []) if mount]


def eligible_disks(disks):
    return [d for d in disks if d.get('type') == 'disk' and not d.get('ro')
            and (d.get('tran') == 'usb' or d.get('rm'))]


def validate_target(disks, device, expected, confirmation, source_dev=None):
    disk = next((d for d in disks if d['name'] == device), None)
    if disk is None or disk not in eligible_disks(disks):
        raise ValueError('Dispositivo non idoneo: selezionare un intero disco USB/rimovibile scrivibile.')
    if not expected or device_token(disk) != expected:
        raise ValueError('Il dispositivo è cambiato: aggiornare la selezione USB.')
    if confirmation != Path(device).name:
        raise ValueError('Conferma di cancellazione non corrispondente al dispositivo.')
    if source_dev and any(n.get('maj:min') == source_dev for n in walk(disk)):
        raise ValueError('La ISO sorgente si trova sul disco selezionato.')
    if mounts(disk):
        raise ValueError('Il disco contiene volumi montati o swap attivo. Smontarli prima di procedere.')
    # Device-mapper, RAID and other holders are forbidden even if not mounted.
    if any(n.get('type') not in {'disk', 'part'} for n in walk(disk)):
        raise ValueError('Il disco è in uso da un volume cifrato, RAID o altro dispositivo.')
    return disk


def source_device(fd):
    number = os.fstat(fd).st_dev
    return f'{os.major(number)}:{os.minor(number)}'
