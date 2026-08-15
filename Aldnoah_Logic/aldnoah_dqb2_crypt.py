# Aldnoah_Logic/aldnoah_dqb2_crypt.py
"""
Dragon Quest Builders 2 LINKDATA payload scrambler
"""
from __future__ import annotations

import os, subprocess, tempfile

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


NATIVE_CLI = os.path.join(os.path.dirname(__file__), "dqb2_crypt_cli.exe")
NATIVE_MIN_BYTES = 65536
NATIVE_TIMEOUT_SECONDS = 60


def native_cli_available() -> bool:
    return os.path.isfile(NATIVE_CLI)


def run_native_cipher(data: bytes, entry_index: int) -> bytes:
    """Run the compiled cipher on one payload, raises on any failure"""
    fd_in, in_path = tempfile.mkstemp(prefix="dqb2c_in_")
    fd_out, out_path = tempfile.mkstemp(prefix="dqb2c_out_")
    try:
        with os.fdopen(fd_in, "wb") as handle:
            handle.write(data)
        os.close(fd_out)

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.run(
            [NATIVE_CLI, str(int(entry_index)), in_path, out_path],
            check=True,
            timeout=NATIVE_TIMEOUT_SECONDS,
            creationflags=creationflags,
            capture_output=True,
        )

        with open(out_path, "rb") as handle:
            result = handle.read()
        if len(result) != len(data):
            raise ValueError(
                f"dqb2_crypt_cli returned {len(result)} bytes for a "
                f"{len(data)} byte payload"
            )
        return result
    finally:
        for path in (in_path, out_path):
            try:
                os.remove(path)
            except OSError:
                pass


def transform_fast(data: bytes, entry_index: int) -> bytes:
    """
    Scramble or descramble a payload, preferring the compiled binary
    """
    if not data:
        return data
    if len(data) >= NATIVE_MIN_BYTES and native_cli_available():
        try:
            return run_native_cipher(data, entry_index)
        except Exception:
            pass
    return transform(data, entry_index)


def native_eligible(size: int) -> bool:
    """Whether a payload of this size is worth handing to the native binary"""
    return size >= NATIVE_MIN_BYTES and native_cli_available()


def run_native_cipher_from_container(container_path: str, offset: int, length: int, entry_index: int) -> bytes:
    """
    Run the compiled cipher directly against a slice of a container file
    """
    fd_out, out_path = tempfile.mkstemp(prefix="dqb2c_out_")
    try:
        os.close(fd_out)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.run(
            [NATIVE_CLI, str(int(entry_index)), container_path, str(int(offset)), str(int(length)), out_path],
            check=True,
            timeout=NATIVE_TIMEOUT_SECONDS,
            creationflags=creationflags,
            capture_output=True,
        )
        with open(out_path, "rb") as handle:
            result = handle.read()
        if len(result) != length:
            raise ValueError(
                f"dqb2_crypt_cli returned {len(result)} bytes for a "
                f"{length} byte slice"
            )
        return result
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


def transform_fast_from_container(container_path: str, offset: int, length: int, entry_index: int):
    """
    Descramble a container slice, preferring the compiled binary
    """
    if length <= 0:
        return b""
    if not native_eligible(length):
        return None
    try:
        return run_native_cipher_from_container(container_path, offset, length, entry_index)
    except Exception:
        return None
