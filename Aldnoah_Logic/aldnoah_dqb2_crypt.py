# Aldnoah_Logic/aldnoah_dqb2_crypt.py
"""
Dragon Quest Builders 2 LINKDATA payload scrambler
"""
from __future__ import annotations

MULT = 0x6C078965
INCR = 0x3039
MASK32 = 0xFFFFFFFF
SEED_BASE = 0xF7114F36

CIPHER_ID = "dqb2"

def seed_for_entry(entry_index: int) -> int:
    """The LCG seed the game uses for one IDX slot"""
    return (SEED_BASE + int(entry_index)) & MASK32

def applies_to(compression_marker: int) -> bool:
    return not compression_marker

def keystream(seed: int, length: int) -> bytes:
    """
    Build the keystream for a payload of the given length
    """
    out = bytearray()
    remaining = int(length)
    state = int(seed) & MASK32

    while remaining > 0:
        if remaining >= 2:
            state = (state * MULT + INCR) & MASK32
            if (state >> 16) & 1:
                state = (state * MULT + INCR) & MASK32
                key = (state >> 16) & 0xFFFF
                out.append(key & 0xFF)
                out.append((key >> 8) & 0xFF)
                remaining -= 2
                continue

        state = (state * MULT + INCR) & MASK32
        d = (state >> 16) & 0xFFFF
        out.append(((d >> 8) & 0xFF) ^ (d & 0xFF))
        remaining -= 1

    return bytes(out)

def transform(data: bytes, entry_index: int) -> bytes:
    """
    Scramble or descramble a payload
    """
    if not data:
        return data
    stream = keystream(seed_for_entry(entry_index), len(data))
    return bytes(a ^ b for a, b in zip(data, stream))

decrypt = transform
encrypt = transform

def transform_if_needed(data: bytes, entry_index: int, compression_marker: int) -> bytes:
    """Apply the cipher only to entries the game actually scrambles"""
    if not applies_to(compression_marker):
        return data
    return transform(data, entry_index)


def entry_index_from_offset(entry_off: int, entry_size: int = 32) -> int:
    """IDX slot index for a byte offset into the IDX"""
    if entry_size <= 0:
        return 0
    return int(entry_off) // int(entry_size)
