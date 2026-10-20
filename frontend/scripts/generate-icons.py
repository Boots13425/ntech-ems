"""Rasterize the application's simple monogram; this is not an official company logo."""
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parents[1] / "public" / "icons"
root.mkdir(exist_ok=True)


def inside_polygon(x, y, points):
    inside = False
    j = len(points) - 1
    for i in range(len(points)):
        xi, yi = points[i]
        xj, yj = points[j]
        if (yi > y) != (yj > y) and x < (xj-xi)*(y-yi)/(yj-yi)+xi:
            inside = not inside
        j = i
    return inside


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def icon(size, filename, maskable=False):
    points = [(17, 46), (17, 18), (24, 18), (40, 37), (40, 18), (47, 18), (47, 46), (40, 46), (24, 27), (24, 46)]
    rows = bytearray()
    for py in range(size):
        rows.append(0)
        for px in range(size):
            x, y = (px + .5) * 64 / size, (py + .5) * 64 / size
            if maskable:
                x, y = (x - 32) / .8 + 32, (y - 32) / .8 + 32
            color = (20, 33, 58)
            if inside_polygon(x, y, points):
                color = (255, 255, 255)
            if (x - 48)**2 + (y - 16)**2 <= 25:
                color = (109, 212, 193)
            rows.extend(color)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b'')
    (root / filename).write_bytes(data)


icon(192, 'icon-192.png')
icon(512, 'icon-512.png')
icon(512, 'maskable-512.png', True)
print('PWA icons generated.')
