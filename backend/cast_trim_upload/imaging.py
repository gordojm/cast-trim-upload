"""Minimal PNG/JPEG header parsing, enough to validate episode artwork."""

import struct


def image_info(data: bytes) -> tuple[str, int, int] | None:
    """Return (extension, width, height) for PNG or JPEG data, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return ".png", width, height

    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            (length,) = struct.unpack(">H", data[i + 2:i + 4])
            # SOF0..SOF15 except DHT (C4), JPG (C8), DAC (CC)
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return ".jpg", width, height
            i += 2 + length
    return None
