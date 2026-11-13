"""The graphics card's load, video memory and temperature, for the GPU card (2026-11-13).

Read through NVIDIA's own monitoring library, nvml.dll, which comes with every NVIDIA driver (System32), via ctypes:
nothing to install, and one reading takes about a millisecond (Windows' "GPU Engine" counters, which Task Manager
uses, take far longer). No NVIDIA card or driver -> read() returns None and the card says so.
The window only asks while it is visible: on a laptop, asking a sleeping graphics card wakes it."""

import ctypes
import sys
from dataclasses import dataclass


@dataclass
class Gpu:
    name: str
    load: float         # percent of the time the GPU was busy (the "3D/compute" load Task Manager shows)
    used_mb: float      # video memory in use
    total_mb: float
    temp_c: int | None


class _Util(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _Memory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


_nvml = None      # the library once loaded and started; False when it can't be (then never tried again)
_handle = None
_name = ""


def _start() -> bool:
    global _nvml, _handle, _name
    if _nvml is not None:
        return bool(_nvml)
    _nvml = False
    if sys.platform != "win32":
        return False
    try:
        lib = ctypes.WinDLL("nvml.dll")
        if lib.nvmlInit_v2() != 0:
            return False
        handle = ctypes.c_void_p()
        if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
            return False
        name = ctypes.create_string_buffer(96)
        if lib.nvmlDeviceGetName(handle, name, 96) == 0:
            _name = name.value.decode(errors="replace").replace("NVIDIA ", "").replace("GeForce ", "")
    except (OSError, AttributeError):
        return False
    _nvml, _handle = lib, handle
    return True


def read() -> Gpu | None:
    """The first NVIDIA card now, or None (no card, no driver, or it didn't answer)."""
    if not _start():
        return None
    util, memory, temp = _Util(), _Memory(), ctypes.c_uint()
    try:
        if _nvml.nvmlDeviceGetUtilizationRates(_handle, ctypes.byref(util)) != 0:
            return None
        has_memory = _nvml.nvmlDeviceGetMemoryInfo(_handle, ctypes.byref(memory)) == 0
        has_temp = _nvml.nvmlDeviceGetTemperature(_handle, 0, ctypes.byref(temp)) == 0  # 0 = the GPU chip
    except OSError:
        return None
    return Gpu(_name or "GPU", float(util.gpu), memory.used / 2 ** 20 if has_memory else 0.0,
               memory.total / 2 ** 20 if has_memory else 0.0, int(temp.value) if has_temp else None)
