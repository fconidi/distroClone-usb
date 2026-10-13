"""Aligned GPT layout with an explicit requested persistence size."""

from dataclasses import asdict, dataclass
import math

MIB = 1024 * 1024


@dataclass(frozen=True)
class Partition:
    start: int
    sectors: int
    kind: str
    name: str


@dataclass(frozen=True)
class Layout:
    sector_size: int
    partitions: tuple[Partition, ...]

    def sfdisk(self):
        lines = ['label: gpt', 'unit: sectors', f'sector-size: {self.sector_size}', '']
        lines += [f'start={p.start}, size={p.sectors}, type={p.kind}, name="{p.name}"'
                  for p in self.partitions]
        return '\n'.join(lines) + '\n'

    def to_dict(self):
        return asdict(self)


def make_layout(disk_bytes, iso_bytes, persistence_mib, sector_size=512):
    if sector_size not in (512, 4096):
        raise ValueError('Dimensione settore non supportata.')
    if not isinstance(persistence_mib, int) or persistence_mib < 512:
        raise ValueError('La persistenza deve essere almeno 512 MiB.')
    if iso_bytes <= 0:
        raise ValueError('ISO vuota.')
    total_mib = disk_bytes // MIB
    data_mib = total_mib - 1 - 2 - 256 - persistence_mib - 1
    minimum_data = math.ceil(iso_bytes / MIB) + max(256, math.ceil(iso_bytes / MIB * .05))
    if data_mib < minimum_data:
        raise ValueError('Spazio insufficiente per ISO, avvio e persistenza richiesta.')
    entries = [(2, '21686148-6449-6E6F-744E-656564454649', 'DCUSB-BIOS'),
               (256, 'C12A7328-F81F-11D2-BA4B-00A0C93EC93B', 'DCUSB-EFI'),
               (data_mib, '0FC63DAF-8483-4772-8E79-3D69D8477DE4', 'DCUSB-DATA'),
               (persistence_mib, '0FC63DAF-8483-4772-8E79-3D69D8477DE4', 'DCUSB-PERSIST')]
    start, partitions = MIB // sector_size, []
    for size, kind, name in entries:
        sectors = size * MIB // sector_size
        partitions.append(Partition(start, sectors, kind, name))
        start += sectors
    return Layout(sector_size, tuple(partitions))
