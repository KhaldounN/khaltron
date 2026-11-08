"""The PC's health: memory Windows can still promise (the real limit for big AI models), RAM and CPU."""

import ctypes
import sys
from dataclasses import dataclass

import psutil


class _Memory(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong), ("total_commit", ctypes.c_ulonglong),
                ("avail_commit", ctypes.c_ulonglong), ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong), ("avail_extended", ctypes.c_ulonglong)]


@dataclass
class Health:
    free_mb: int        # what a new program can still get: the smaller of free RAM and Windows' remaining commit
    total_mb: int       # RAM
    ram_free_mb: int
    commit_free_mb: int | None
    cpu: float          # percent of the whole CPU


def read() -> Health:
    ram = psutil.virtual_memory()
    ram_free = int(ram.available / 2 ** 20)
    commit = None
    if sys.platform == "win32":
        status = _Memory()
        status.length = ctypes.sizeof(_Memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            commit = int(status.avail_commit / 2 ** 20)
    free = min(ram_free, commit) if commit is not None else ram_free
    return Health(free, int(ram.total / 2 ** 20), ram_free, commit, psutil.cpu_percent(None))
