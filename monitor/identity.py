"""Khaltron's identity in Windows, so its notifications say "Khaltron 9000" with the raccoon's face.

Without this, Windows names every notification after the program that sent it: Khaltron runs inside Python, so
they said "Python" with Python's icon. Windows lets a program give itself an application ID (an AppUserModelID)
and look up that ID's display name and icon in the registry (HKEY_CURRENT_USER, so no administrator rights).
Set once at start-up, before the tray icon is made."""

import sys

from .config import HOME
from .theme import NAME

APP_ID = "KhaldounN.Khaltron9000"
ICON = HOME / "assets" / "khaltron.png"


def claim() -> bool:
    """Register the ID's name and icon (current user only) and adopt it for this process. False if not Windows."""
    if sys.platform != "win32":
        return False
    import ctypes
    import winreg
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, NAME)
            if ICON.exists():
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(ICON))
            winreg.SetValueEx(key, "IconBackgroundColor", 0, winreg.REG_SZ, "FF05070A")
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        return True
    except OSError:
        return False
